using System;
using System.Reflection;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;
using System.Linq;

namespace TestApi
{
    class Test
    {
        static void Main()
        {
            var methods = typeof(Rebar).GetMethods(BindingFlags.Public | BindingFlags.Static)
                .Where(m => m.Name.Contains("CreateFrom"))
                .Select(m => m.Name + "(" + string.Join(", ", m.GetParameters().Select(p => p.ParameterType.Name)) + ")")
                .ToList();
            foreach(var m in methods) Console.WriteLine(m);
        }
    }
}
