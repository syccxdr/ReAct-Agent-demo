import json
import pathlib
import pandas as pd
import streamlit as st


TRACE_PATH = "./data/output/trace.jsonl"


def load_trace_df() -> pd.DataFrame:
    p = pathlib.Path(TRACE_PATH)
    if not p.exists():
        return pd.DataFrame()
    rows = []
    with p.open("r", encoding="utf-8") as f:
        for ln in f:
            try:
                rows.append(json.loads(ln))
            except Exception:
                continue
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


st.set_page_config(page_title="Agent Trace Viewer", layout="wide")
st.title("🤖 Agent Trace Viewer")

df = load_trace_df()
if df.empty:
    st.info("No trace yet. Run the agent to generate ./data/output/trace.jsonl")
    st.stop()

sessions = sorted(df["session_id"].dropna().unique().tolist())
types = sorted(df["type"].dropna().unique().tolist())

col1, col2, col3 = st.columns(3)
session = col1.selectbox("Session", ["(all)"] + sessions)
selected = col2.multiselect("Types", types, default=types)
kw = col3.text_input("Keyword", "")

f = df.copy()
if session != "(all)":
    f = f[f["session_id"] == session]
if selected:
    f = f[f["type"].isin(selected)]
if kw:
    k = kw.lower()
    f = f[f.astype(str).apply(lambda r: k in r.to_string().lower(), axis=1)]

st.subheader("Timeline")
cols = [c for c in ["step","type","phase","status","tool","duration_ms","prompt_preview","model_response_preview","result_preview","raw","reason","kind","msg","api_calls","token_in","token_out"] if c in f.columns]
st.dataframe(f.sort_values(["step","ts"])[cols].fillna(""), use_container_width=True, height=420)

st.subheader("Stats")
api_calls = int(f.get("api_calls", pd.Series([0])).max()) if "api_calls" in f else 0
token_in = int(f.get("token_in", pd.Series([0])).sum()) if "token_in" in f else 0
token_out = int(f.get("token_out", pd.Series([0])).sum()) if "token_out" in f else 0
st.write(f"- API calls: {api_calls}")
st.write(f"- Tokens in: {token_in}, out: {token_out}")

st.subheader("Errors")
err = f[f["type"] == "error"]
if not err.empty:
    st.dataframe(err[[c for c in ["step","kind","msg","reason","tool"] if c in err.columns]].fillna(""), use_container_width=True, height=240)
else:
    st.write("No errors recorded in current filter.")


