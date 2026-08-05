from __future__ import annotations

import json
import platform
from datetime import datetime

from app.config import get_model_name
from app.olist_tools import METADATA_PATH, OlistCaseTools


def main() -> None:
    tools = OlistCaseTools()
    result = tools.run_all_cases(reset_trace=True)
    metadata = {
        "model": get_model_name(),
        "parameter_size": "<=10B or provider model as configured",
        "framework": "LangChain create_agent + deterministic Python CSV tools",
        "runtime": {
            "python": platform.python_version(),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "processed_cases": result["processed"],
    }
    METADATA_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
