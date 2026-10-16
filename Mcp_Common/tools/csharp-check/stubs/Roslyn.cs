// STUB toi thieu cua Microsoft.CodeAnalysis.CSharp.Scripting - chi de kiem tra mcs bien dich duoc ma nguon cua ta.
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
namespace Microsoft.CodeAnalysis
{
    public abstract class MetadataReference { public static PortableExecutableReference CreateFromFile(string path) { return null; } }
    public class PortableExecutableReference : MetadataReference { }
    public enum DiagnosticSeverity { Hidden, Info, Warning, Error }
    public abstract class Diagnostic { public DiagnosticSeverity Severity { get { return DiagnosticSeverity.Error; } } }
}
namespace Microsoft.CodeAnalysis.Scripting
{
    public class ScriptOptions
    {
        public static ScriptOptions Default { get { return new ScriptOptions(); } }
        public ScriptOptions WithReferences(IEnumerable<MetadataReference> refs) { return this; }
        public ScriptOptions WithImports(IEnumerable<string> imports) { return this; }
        public ScriptOptions WithEmitDebugInformation(bool b) { return this; }
    }
    public class ScriptState<T> { public T ReturnValue { get; } }
    public abstract class Script<T>
    {
        public abstract IEnumerable<Diagnostic> Compile(CancellationToken ct = default(CancellationToken));
        public abstract Task<ScriptState<T>> RunAsync(object globals = null, CancellationToken ct = default(CancellationToken));
    }
}
namespace Microsoft.CodeAnalysis.CSharp.Scripting
{
    public static class CSharpScript
    {
        public static Microsoft.CodeAnalysis.Scripting.Script<T> Create<T>(string code, Microsoft.CodeAnalysis.Scripting.ScriptOptions options = null, Type globalsType = null) { return null; }
    }
}
