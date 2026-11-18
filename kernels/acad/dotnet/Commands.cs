using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;

[assembly: CommandClass(typeof(AcadKit.Plugin.Commands))]

namespace AcadKit.Plugin
{
    /// <summary>
    /// acadkit 的 .NET 插件骨架。
    ///
    /// 为什么要有它：acadkit 主路径走 ActiveX/命令行，有 4 条能力卡在进程外够不着
    /// （dim.associative / block.edit_inplace / layer.state / solid.revolve）。
    /// 这些 API 只在**进程内**托管代码里可用，所以需要这个插件作为"第二条通道"。
    ///
    /// 设计约定：**每条命令都把结果写回图面**（一行 MText：`AKRESULT &lt;tag&gt;: ...`），
    /// 而不是只 PrintMessage。这样 Python 侧可以用既有的"读回"机制验证，
    /// 不依赖命令行文本、也不依赖返回值 —— 与 acadkit 的判据纪律一致。
    /// </summary>
    public static class Commands
    {
        public const string ResultPrefix = "AKRESULT";
        public const string PluginVersion = "1.0.0";

        // ── 公共设施 ────────────────────────────────────────────────
        private static void WriteResult(string tag, string text)
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;
            var db = doc.Database;
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                var ms = (BlockTableRecord)tr.GetObject(
                    bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);
                var mt = new MText();
                mt.Contents = string.Format("{0} {1}: {2}", ResultPrefix, tag, text);
                mt.Location = new Point3d(0, -120, 0);
                mt.TextHeight = 2.5;
                ms.AppendEntity(mt);
                tr.AddNewlyCreatedDBObject(mt, true);
                tr.Commit();
            }
            doc.Editor.WriteMessage("\n{0} {1}: {2}", ResultPrefix, tag, text);
        }

        // ── 1) 证明插件已加载 ───────────────────────────────────────
        [CommandMethod("ACADKITVERSION")]
        public static void Version()
        {
            WriteResult("VERSION", string.Format(
                "plugin={0} clr={1} acad={2}",
                PluginVersion,
                Environment.Version,
                Application.Version));
        }

        // ── 2) solid.revolve：进程内 CreateRevolvedSolid ────────────
        [CommandMethod("ACADKITREVOLVE")]
        public static void Revolve()
        {
            try
            {
                var doc = Application.DocumentManager.MdiActiveDocument;
                var db = doc.Database;
                double volume;
                ObjectId solidId;
                using (var tr = db.TransactionManager.StartTransaction())
                {
                    var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                    var ms = (BlockTableRecord)tr.GetObject(
                        bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);

                    // 轮廓：x 5..25、y 0..10 的矩形（绕 Y 轴转 360° → 空心圆柱）
                    var pl = new Polyline();
                    pl.AddVertexAt(0, new Point2d(5, 0), 0, 0, 0);
                    pl.AddVertexAt(1, new Point2d(25, 0), 0, 0, 0);
                    pl.AddVertexAt(2, new Point2d(25, 10), 0, 0, 0);
                    pl.AddVertexAt(3, new Point2d(5, 10), 0, 0, 0);
                    pl.Closed = true;
                    ms.AppendEntity(pl);
                    tr.AddNewlyCreatedDBObject(pl, true);

                    var curves = new DBObjectCollection();
                    curves.Add(pl);
                    var regions = Region.CreateFromCurves(curves);
                    var region = (Region)regions[0];

                    var solid = new Solid3d();
                    // 实测签名（acdbmgd, AutoCAD 2025）：
                    //   CreateRevolvedSolid(Entity profile, Point3d axisPoint,
                    //                       Vector3d axisDir, double angle,
                    //                       double startAngle, RevolveOptions opt)
                    var opts = new RevolveOptions();   // AutoDelete 只读，不设
                    solid.CreateRevolvedSolid(
                        region,
                        new Point3d(0, 0, 0),          // 轴上一点
                        new Vector3d(0, 1, 0),         // 绕 Y 轴
                        2.0 * Math.PI,                 // 一整圈
                        0.0,
                        opts);
                    ms.AppendEntity(solid);
                    tr.AddNewlyCreatedDBObject(solid, true);

                    volume = solid.MassProperties.Volume;
                    solidId = solid.ObjectId;
                    tr.Commit();
                }
                double expected = Math.PI * (25.0 * 25.0 - 5.0 * 5.0) * 10.0;
                WriteResult("REVOLVE", string.Format(
                    "handle={0} volume={1:F1} expected={2:F1} ratio={3:F4}",
                    solidId.Handle, volume, expected, volume / expected));
            }
            catch (System.Exception ex)
            {
                WriteResult("REVOLVE", "error=" + ex.GetType().Name + ": " + ex.Message);
            }
        }

        // ── 3) layer.state：进程内 LayerStateManager ────────────────
        [CommandMethod("ACADKITLAYERSTATE")]
        public static void LayerState()
        {
            try
            {
                var doc = Application.DocumentManager.MdiActiveDocument;
                var db = doc.Database;
                const string stateName = "AK_LS_PROBE";
                int savedCount, restoredOk;
                string before, after, changed;
                using (var tr = db.TransactionManager.StartTransaction())
                {
                    var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
                    foreach (var name in new[] { "AK_LS_A", "AK_LS_B" })
                    {
                        if (!lt.Has(name))
                        {
                            tr.GetObject(db.LayerTableId, OpenMode.ForWrite);
                            var ltr = new LayerTableRecord { Name = name };
                            lt.UpgradeOpen();
                            lt.Add(ltr);
                            tr.AddNewlyCreatedDBObject(ltr, true);
                        }
                    }
                    tr.Commit();
                }

                var lsm = db.LayerStateManager;
                // 实测签名：
                //   SaveLayerState(string name, LayerStateMasks mask, ObjectId id)
                //   RestoreLayerState(string name, ObjectId id, int policy, LayerStateMasks clientMask)
                var saveMask = LayerStateMasks.Color | LayerStateMasks.On;
                lsm.SaveLayerState(stateName, saveMask, ObjectId.Null);
                savedCount = lsm.GetLayerStateNames(false, false).Count;

                before = ReadLayerColor(db, "AK_LS_A");
                SetLayerColor(db, "AK_LS_A", 30);           // 改颜色
                changed = ReadLayerColor(db, "AK_LS_A");
                lsm.RestoreLayerState(stateName, ObjectId.Null, 0,
                    LayerStateMasks.Color);
                after = ReadLayerColor(db, "AK_LS_A");
                restoredOk = after == before ? 1 : 0;

                WriteResult("LAYERSTATE", string.Format(
                    "states={0} name={1} before={2} changed={3} after={4} restored={5}",
                    savedCount, stateName, before, changed, after, restoredOk));
            }
            catch (System.Exception ex)
            {
                WriteResult("LAYERSTATE", "error=" + ex.GetType().Name + ": " + ex.Message);
            }
        }

        private static string ReadLayerColor(Database db, string name)
        {
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
                if (!lt.Has(name)) return "missing";
                var ltr = (LayerTableRecord)tr.GetObject(lt[name], OpenMode.ForRead);
                return ltr.Color.ColorIndex.ToString();
            }
        }

        private static void SetLayerColor(Database db, string name, short index)
        {
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
                var ltr = (LayerTableRecord)tr.GetObject(lt[name], OpenMode.ForWrite);
                ltr.Color = Autodesk.AutoCAD.Colors.Color.FromColorIndex(
                    Autodesk.AutoCAD.Colors.ColorMethod.ByAci, index);
                tr.Commit();
            }
        }

        // ── 4) 尚未实现的解锁点（明确报告，不假装成功）────────────
        [CommandMethod("ACADKITEDITBLOCK")]
        public static void EditBlock()
        {
            WriteResult("EDITBLOCK",
                "not-implemented: BlockEditor 需要 UI 模式，留待下一阶段");
        }

        [CommandMethod("ACADKITASSOC")]
        public static void AssociativeDim()
        {
            WriteResult("ASSOC",
                "not-implemented: 关联标注需要 DimAssoc + 几何关联表，留待下一阶段");
        }

        [CommandMethod("ACADKITINFO")]
        public static void Info()
        {
            WriteResult("INFO", string.Format(
                "plugin={0} commands=ACADKITVERSION,ACADKITREVOLVE,ACADKITLAYERSTATE,ACADKITEDITBLOCK,ACADKITASSOC",
                PluginVersion));
        }
    }
}
