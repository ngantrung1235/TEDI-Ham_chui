// STUB toi thieu cua Autodesk.Navisworks.Api (theo chu ky MA TA GIA DINH) - chi de mcs kiem tra mach lac ma nguon cua ta.
using System;
using System.Collections;
using System.Collections.Generic;
namespace Autodesk.Navisworks.Api
{
    public class VariantData
    {
        public static VariantData FromDisplayString(string s) { return null; }
        public string ToDisplayString() { return null; }
    }
    public class DataProperty { public string DisplayName { get; } public string Name { get; } public VariantData Value { get; } }
    public class DataPropertyCollection : IEnumerable<DataProperty> { public IEnumerator<DataProperty> GetEnumerator() { return null; } IEnumerator IEnumerable.GetEnumerator() { return null; } }
    public class PropertyCategory { public string DisplayName { get; } public string Name { get; } public DataPropertyCollection Properties { get; } }
    public class PropertyCategoryCollection : IEnumerable<PropertyCategory> { public IEnumerator<PropertyCategory> GetEnumerator() { return null; } IEnumerator IEnumerable.GetEnumerator() { return null; } }
    public class ModelItemEnumerableCollection : IEnumerable<ModelItem> { public IEnumerator<ModelItem> GetEnumerator() { return null; } IEnumerator IEnumerable.GetEnumerator() { return null; } }
    public class ModelItem
    {
        public string DisplayName { get; }
        public bool HasGeometry { get; }
        public ModelItem Parent { get; }
        public ModelItemEnumerableCollection Children { get; }
        public ModelItemEnumerableCollection DescendantsAndSelf { get; }
        public PropertyCategoryCollection PropertyCategories { get; }
        public string ClassDisplayName { get; }
        public BoundingBox3D BoundingBox() { return null; }
    }
    public class Point3D { public double X, Y, Z; }
    public class BoundingBox3D { public Point3D Min, Max; }
    public class ModelItemCollection : IEnumerable<ModelItem>
    {
        public int Count { get { return 0; } }
        public void Add(ModelItem m) { }
        public IEnumerator<ModelItem> GetEnumerator() { return null; } IEnumerator IEnumerable.GetEnumerator() { return null; }
    }
    public class Selection
    {
        public ModelItemCollection SelectedItems { get { return null; } }
        public void Clear() { }
        public void CopyFrom(ModelItemCollection c) { }
    }
    public class DocumentModels : IEnumerable<object>
    {
        public ModelItemEnumerableCollection RootItems { get { return null; } }
        public IEnumerator<object> GetEnumerator() { return null; } IEnumerator IEnumerable.GetEnumerator() { return null; }
    }
    public class Document
    {
        public DocumentModels Models { get { return null; } }
        public Selection CurrentSelection { get { return null; } }
    }
    public static class Application { public static Document ActiveDocument { get { return null; } } }
    public class SearchCondition
    {
        public static SearchCondition HasPropertyByDisplayName(string cat, string prop) { return null; }
        public SearchCondition EqualValue(VariantData v) { return this; }
    }
    public class SearchConditionCollection { public void Add(SearchCondition c) { } }
    public class SelectionSource { public void SelectAll() { } }
    public class Search
    {
        public SelectionSource Selection { get { return null; } }
        public SearchConditionCollection SearchConditions { get { return null; } }
        public ModelItemCollection FindAll(Document d, bool visibleOnly) { return null; }
    }
}
namespace Autodesk.Navisworks.Api.Plugins
{
    public enum AddInLocation { None, AddIn }
    [AttributeUsage(AttributeTargets.Class)] public class PluginAttribute : Attribute { public PluginAttribute(string name, string dev) { } public string DisplayName { get; set; } public string ToolTip { get; set; } }
    [AttributeUsage(AttributeTargets.Class)] public class AddInPluginAttribute : Attribute { public AddInPluginAttribute(AddInLocation l) { } }
    public abstract class EventWatcherPlugin { public virtual void OnLoaded() { } public virtual void OnUnloading() { } }
    public abstract class AddInPlugin { public abstract int Execute(params string[] parameters); }
}
