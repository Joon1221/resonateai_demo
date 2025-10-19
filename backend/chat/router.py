import json
from typing import Dict, Any

from . import tools

TOOL_FNS = {
    "verify_patient": tools.verify_patient,
    "list_appointments": tools.list_appointments,
    "find_slots": tools.find_slots,
    "book_appointment": tools.book_appointment,
    "reschedule_appointment": tools.reschedule_appointment,
    "cancel_appointment": tools.cancel_appointment,
    "create_staff_alert": tools.create_staff_alert,
}


def maybe_parse_tool_call(text: str) -> Dict[str, Any] | None:
    """
    If assistant responded with a JSON tool call (per your prompt contract),
    return {"tool": "...", "parameters": {...}} else None.
    """
    s = text.strip()

    if "{\"tool\":" not in s:
        return None
    try:
        start_index = s.find("{\"tool\":")
        count = 0
        for i in range(start_index, len(s)):
            if s[i] == "{":
                count += 1
            elif s[i] == "}":
                count -= 1
            if count == 0:
                break
            end_index = i + 1
        s = s[start_index:end_index+1]
        print(s)
        obj = json.loads(s)
        if isinstance(obj, dict) and "tool" in obj and "parameters" in obj:
            return obj
    except Exception:
        pass
    return None

def execute_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    fn = TOOL_FNS.get(tool_name)
    if not fn:
        return {"ok": False, "error": f"unknown_tool:{tool_name}"}
    try:
        return fn(params)
    except Exception as e:
        return {"ok": False, "error": str(e)}
