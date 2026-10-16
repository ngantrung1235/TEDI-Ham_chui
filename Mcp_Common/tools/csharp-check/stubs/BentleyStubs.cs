// STUB toi thieu cua SDK Bentley (theo chu ky MA TA GIA DINH) - chi de mcs kiem tra mach lac ma nguon cua ta.
using System;
using System.Collections;
using System.Collections.Generic;
namespace Bentley.GeometryNET
{
    public struct DPoint3d { public double X, Y, Z; public DPoint3d(double x, double y, double z) { X = x; Y = y; Z = z; } }
    public struct DVector3d { public double X, Y, Z; public DVector3d(double x, double y, double z) { X = x; Y = y; Z = z; } }
    public struct DRange3d { public DPoint3d Low, High; }
    public abstract class CurvePrimitive { public static CurvePrimitive CreateChildCurveVector(CurveVector cv) { return null; } }
    public class CurveVector
    {
        public enum BoundaryType { None, Open, Outer, Inner, ParityRegion, UnionRegion }
        public CurveVector(BoundaryType t) { }
        public static CurveVector CreateLinear(IList<DPoint3d> pts, BoundaryType t, bool b) { return null; }
        public void Add(CurvePrimitive p) { }
    }
    public class DgnExtrusionDetail { public DgnExtrusionDetail(CurveVector cv, DVector3d v, bool cap) { } }
    public abstract class SolidPrimitive { public static SolidPrimitive CreateDgnExtrusion(DgnExtrusionDetail d) { return null; } }
}
namespace Bentley.DgnPlatformNET
{
    using Bentley.GeometryNET;
    public enum StatusInt { Success = 0 }
    public struct ElementId { public ElementId(ref long id) { } public override string ToString() { return "0"; } }
    public class ModelInfo { public double UorPerMeter, UorPerMaster; public DPoint3d GlobalOrigin; }
    public class LevelHandle { public bool IsValid; public string Name; public ElementId LevelId; }
    public class LevelCache { public LevelHandle GetLevelByName(string n) { return null; } public LevelHandle GetLevel(ElementId id) { return null; } }
    public class DgnFile { public LevelCache GetLevelCache() { return null; } }
    public class DgnModel
    {
        public ModelInfo GetModelInfo() { return null; }
        public IEnumerable<Elements.Element> GetGraphicElements() { return null; }
        public Elements.Element FindElementById(ElementId id) { return null; }
    }
    public class ElementPropertiesGetter { public ElementPropertiesGetter(Elements.Element e) { } public ElementId Level { get { return default(ElementId); } } }
    public class ElementPropertiesSetter { public void SetLevel(ElementId id) { } public bool Apply(Elements.Element e) { return true; } }
    public static class SelectionSetManager
    {
        public static void EmptyAll() { }
        public static void AddElement(Elements.Element e, DgnModel m) { }
    }
    public static class DraftingElementSchema { public static Elements.Element ToElement(DgnModel m, SolidPrimitive s, Elements.Element template) { return null; } }
}
namespace Bentley.DgnPlatformNET.Elements
{
    using Bentley.GeometryNET;
    public enum MSElementType { Line }
    public abstract class Element
    {
        public ElementId ElementId { get { return default(ElementId); } }
        public MSElementType ElementType { get { return default(MSElementType); } }
        public string TypeName { get { return null; } }
        public string Description { get { return null; } }
        public StatusInt AddToModel() { return StatusInt.Success; }
        public StatusInt DeleteFromModel() { return StatusInt.Success; }
    }
    public abstract class DisplayableElement : Element { public StatusInt CalcElementRange(out DRange3d r) { r = default(DRange3d); return StatusInt.Success; } }
    public class ShapeElement : DisplayableElement { public ShapeElement(DgnModel m, Element t, DPoint3d[] pts) { } }
    public class LineStringElement : DisplayableElement { public LineStringElement(DgnModel m, Element t, DPoint3d[] pts) { } }
}
namespace Bentley.DgnPlatformNET.DgnEC
{
    using Bentley.DgnPlatformNET.Elements;
    using Bentley.ECObjects.Instance;
    [Flags] public enum ECQueryProcessFlags { SearchAllClasses = 1 }
    public interface IDgnECInstance : IEnumerable<IECPropertyValue>
    {
        Bentley.ECObjects.Schema.IECClass ClassDefinition { get; }
    }
    public class DgnECInstanceCollection : IEnumerable<IDgnECInstance>, IDisposable
    {
        public IEnumerator<IDgnECInstance> GetEnumerator() { return null; }
        IEnumerator IEnumerable.GetEnumerator() { return null; }
        public void Dispose() { }
    }
    public class DgnECManager
    {
        public static DgnECManager Manager { get { return null; } }
        public DgnECInstanceCollection GetElementProperties(Element e, ECQueryProcessFlags f) { return null; }
    }
}
namespace Bentley.ECObjects.Schema
{
    public interface IECSchema { string Name { get; } }
    public interface IECClass { string Name { get; } string DisplayLabel { get; } IECSchema Schema { get; } }
    public interface IECProperty { string Name { get; } }
}
namespace Bentley.ECObjects.Instance
{
    public interface IECPropertyValue : IEnumerable<IECPropertyValue>
    {
        Bentley.ECObjects.Schema.IECProperty Property { get; }
        bool IsNull { get; }
        string StringValue { get; }
    }
    public interface IECStructValue : IECPropertyValue { }
    public interface IECArrayValue : IECPropertyValue { int Count { get; } IECPropertyValue this[int i] { get; } }
}
namespace Bentley.MstnPlatformNET
{
    public class Session { public static Session Instance { get { return null; } } public Bentley.DgnPlatformNET.DgnFile GetActiveDgnFile() { return null; } public Bentley.DgnPlatformNET.DgnModel GetActiveDgnModel() { return null; } }
    public class MessageCenter { public static MessageCenter Instance { get { return null; } } public void ShowInfoMessage(string a, string b, bool c) { } public void ShowErrorMessage(string a, string b, bool c) { } }
    [AttributeUsage(AttributeTargets.Class)] public class AddInAttribute : Attribute { public string MdlTaskID { get; set; } public string KeyinTree { get; set; } }
    public class UnloadingEventArgs : EventArgs { }
    public abstract class AddIn
    {
        protected AddIn(IntPtr mdlDesc) { }
        protected abstract int Run(string[] commandLine);
        protected virtual void OnUnloading(UnloadingEventArgs e) { }
    }
    namespace InteropServices { public static class Utilities { public static Bentley.Interop.MicroStationDGN.Application ComApp { get { return null; } } } }
}
namespace Bentley.Interop.MicroStationDGN
{
    public struct Point3d { public double X, Y, Z; }
    public class Level { public string Name; public string Description; public bool IsDisplayed; }
    public class Levels : IEnumerable<Level> { public Level this[string n] { get { return null; } } public void Rewrite() { } public IEnumerator<Level> GetEnumerator() { return null; } IEnumerator IEnumerable.GetEnumerator() { return null; } }
    public class Element { public long ID; }
    public class ElementEnumerator { public bool MoveNext() { return false; } public Element Current; }
    public class ModelReference { public string Name; public string Description; public int Type; public bool Is3D; public ElementEnumerator GetSelectedElements() { return null; } }
    public class ModelReferences : IEnumerable<ModelReference> { public IEnumerator<ModelReference> GetEnumerator() { return null; } IEnumerator IEnumerable.GetEnumerator() { return null; } }
    public class DesignFile { public string FullName; public bool ReadOnly; public ModelReferences Models; public Levels Levels; public void Save() { } public Level AddNewLevel(string n) { return null; } }
    public class CadInputQueue { public void SendKeyin(string k) { } public void SendDataPoint(Point3d p, int v) { } public void SendReset() { } }
    public class Settings { public Level Level { get; set; } }
    public class Application
    {
        public string Name; public string Version;
        public DesignFile ActiveDesignFile; public ModelReference ActiveModelReference; public Settings ActiveSettings; public CadInputQueue CadInputQueue;
        public void OpenDesignFile(string p, bool ro) { }
        public object GetCExpressionValue(string e) { return null; }
        public object GetCExpressionValue(string e, string app) { return null; }
    }
}
