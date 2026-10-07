"""2026-10-07 team decision: GPT-5 mini is the default language model; GPT-5 nano stays selectable through DESK_LLM_MODEL.

    python 实验/patches/patch_default_mini.py <repo>
"""
import sys
from pathlib import Path

R = Path(sys.argv[1])


def patch(rel, pairs):
    p = R / rel
    s = p.read_text(encoding="utf-8")
    for a, b in pairs:
        assert s.count(a) == 1, (rel, s.count(a), a[:60])
        s = s.replace(a, b)
    p.write_text(s, encoding="utf-8", newline="")


patch("llm/llm_client.py", [
    ('"""LLM client (OpenAI GPT-5 nano via the Responses API) + the rule-based fallback parser.',
     '"""LLM client (OpenAI GPT-5 mini by default, via the Responses API) + the rule-based fallback parser.'),
    ("    DESK_LLM_MODEL             model id           (default gpt-5-nano)",
     "    DESK_LLM_MODEL             model id           (default gpt-5-mini; gpt-5-nano is about 4x cheaper)"),
    ('DEFAULT_MODEL = "gpt-5-nano"', 'DEFAULT_MODEL = "gpt-5-mini"          # team decision 2026-10-07; see docs/round2_changes.md'),
    ('description="Parse the 30 official requests with rules (default) or GPT-5 nano (--llm).")',
     'description="Parse the 30 official requests with rules (default) or the LLM (--llm, default GPT-5 mini).")'),
])

patch(".env.example", [
    ("# openai = call GPT-5 nano; none = rule-based parser only (no network, no cost)",
     "# openai = call the GPT-5 model below; none = rule-based parser only (no network, no cost)"),
    ("# Cheapest GPT-5 model; enough for field extraction.\nDESK_LLM_MODEL=gpt-5-nano",
     "# Team default since 2026-10-07: right behaviour on both test inboxes in round 2.\n"
     "# gpt-5-nano is about 4x cheaper but misreads one phrasing (docs/round2_changes.md, known issues).\n"
     "DESK_LLM_MODEL=gpt-5-mini"),
])

patch("app/streamlit_app.py", [
    ('    parser_choice = st.radio("Message parser", ["Rules (free, offline)", "GPT-5 nano"], index=1 if st.session_state.use_llm else 0,',
     '    llm_label = (os.getenv("DESK_LLM_MODEL") or DEFAULT_MODEL).replace("gpt-", "GPT-").replace("-mini", " mini").replace("-nano", " nano")\n'
     '    parser_choice = st.radio("Message parser", ["Rules (free, offline)", llm_label], index=1 if st.session_state.use_llm else 0,'),
    ('    want_llm = parser_choice == "GPT-5 nano"', '    want_llm = parser_choice == llm_label'),
    ('        st.caption(f"GPT-5 nano spend this session: ${c.spent_usd:.4f} of ${c.budget_usd:.2f}")',
     '        st.caption(f"{c.model} spend this session: ${c.spent_usd:.4f} of ${c.budget_usd:.2f}")'),
    ("(add `--parser llm --runs 3` for GPT-5 nano)", "(add `--parser llm --runs 3` for the LLM)"),
])

patch("desk/pipeline.py", [
    ("    python desk/pipeline.py --llm            # GPT-5 nano extraction (costs money; needs .env)",
     "    python desk/pipeline.py --llm            # LLM extraction, GPT-5 mini by default (costs money; needs .env)"),
    ('help="use GPT-5 nano for parsing (costs money)")', 'help="use the LLM for parsing, GPT-5 mini by default (costs money)")'),
])

patch("eval/run_language_eval.py", [
    ("--parser llm --runs 3 # GPT-5 nano, costs money", "--parser llm --runs 3 # GPT-5 mini by default, costs money"),
    ('help="LLM model id (default: DESK_LLM_MODEL or gpt-5-nano)")', 'help="LLM model id (default: DESK_LLM_MODEL or gpt-5-mini)")'),
])
print("default model -> gpt-5-mini")
