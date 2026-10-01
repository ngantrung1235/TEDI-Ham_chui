using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;

namespace BentleyMcp.Infrastructure
{
    internal delegate object RpcHandler(JObject p);

    internal sealed class RpcEntry
    {
        public string Name;
        public bool OnMainThread;
        public RpcHandler Handler;
        public string Description;
    }

    internal sealed class RpcRegistry
    {
        private readonly Dictionary<string, RpcEntry> _entries = new Dictionary<string, RpcEntry>(StringComparer.OrdinalIgnoreCase);

        // mainThread = true: handler cham vao API MicroStation -> chay qua MainThread.Invoke.
        public void Add(string name, bool mainThread, string description, RpcHandler handler)
        {
            _entries[name] = new RpcEntry { Name = name, OnMainThread = mainThread, Handler = handler, Description = description };
        }

        public bool TryGet(string name, out RpcEntry entry) => _entries.TryGetValue(name, out entry);

        public IEnumerable<RpcEntry> All => _entries.Values;
    }
}
