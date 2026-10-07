"""One-off patch (round 2): the standing constraints are a tool output too.

Found by looking at the UI: after a bulk confirm, R09's card said "untraced numbers: 08, 48". The reply
now says when a standing constraint was set ("set at 08:48, after this request arrived"), and that time
was not in any tool output. The constraint register is now recorded as a tool call whenever it applies,
so the time, the source message and who set it are all traceable like every other number.
"""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "desk" / "pipeline.py"
s = p.read_text(encoding="utf-8")
a = '''        excl = self.exclusions_for(req)
        pref = req["preference"]'''
b = '''        excl = self.exclusions_for(req)
        if self.session_excl:
            d["tool_calls"].append({"tool": "standing_constraints",
                                    "output": {wid: {"workshop": self.name(wid), "by": v["by"], "source": v["source"], "time": v.get("time", "")}
                                               for wid, v in self.session_excl.items()}})
        pref = req["preference"]'''
assert s.count(a) == 1, s.count(a)
p.write_text(s.replace(a, b), encoding="utf-8", newline="")
print("constraint tool call patched")
