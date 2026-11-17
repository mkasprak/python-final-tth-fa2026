from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import streamlit as st


APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR / "final_project"
MENU_PATH = PROJECT_DIR / "menu.txt"
EMPLOYEE_PATH = PROJECT_DIR / "employee.txt"
ORDER_HISTORY_PATH = PROJECT_DIR / "order_history.txt"


@dataclass(frozen=True)
class Menu:
    drink_types: list[str]
    sizes: list[str]
    prices: list[float]
    milks: list[str]
    flavors: list[str]


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def load_menu(path: Path = MENU_PATH) -> Menu:
    menu_map: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if ":" not in line:
                continue
            category, detail = line.split(":", 1)
            menu_map[category.strip().upper()] = detail.strip()

    drink_types = _split_csv(menu_map.get("DRINK_TYPE", ""))
    sizes = _split_csv(menu_map.get("SIZES", ""))
    milks = _split_csv(menu_map.get("MILKS", ""))
    flavors = _split_csv(menu_map.get("FLAVORS", ""))

    prices_raw = _split_csv(menu_map.get("PRICES", ""))
    prices: list[float] = []
    for p in prices_raw:
        try:
            prices.append(float(p))
        except ValueError:
            prices.append(0.0)

    if len(prices) < len(sizes):
        prices.extend([0.0] * (len(sizes) - len(prices)))
    if len(prices) > len(sizes):
        prices = prices[: len(sizes)]

    return Menu(
        drink_types=drink_types,
        sizes=sizes,
        prices=prices,
        milks=milks,
        flavors=flavors,
    )


def _ensure_data_files() -> None:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    if not EMPLOYEE_PATH.exists():
        EMPLOYEE_PATH.write_text("", encoding="utf-8")
    if not ORDER_HISTORY_PATH.exists():
        ORDER_HISTORY_PATH.write_text("", encoding="utf-8")


def read_employee(emp_id: str) -> Optional[dict[str, Any]]:
    if not EMPLOYEE_PATH.exists():
        return None

    # If there are duplicates, take the most recent one (last match wins).
    found: Optional[dict[str, Any]] = None
    for line in EMPLOYEE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        line_id, raw = line.split(":", 1)
        if line_id.strip() != emp_id.strip():
            continue
        try:
            parsed = ast.literal_eval(raw.strip())
            if isinstance(parsed, dict):
                found = parsed
        except Exception:
            continue
    return found


def append_employee(emp_id: str, record: dict[str, Any]) -> None:
    safe_id = emp_id.strip()
    with EMPLOYEE_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{safe_id}:{record}\n")


def append_order(order: dict[str, Any]) -> None:
    with ORDER_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(order, ensure_ascii=False) + "\n")


def read_orders(limit: int = 200) -> list[dict[str, Any]]:
    if not ORDER_HISTORY_PATH.exists():
        return []
    lines = ORDER_HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    orders: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            orders.append(parsed)
    return orders


def _init_state() -> None:
    st.session_state.setdefault("step", "Employee")
    st.session_state.setdefault("employee_id", "")
    st.session_state.setdefault("employee_record", None)
    st.session_state.setdefault("order", None)


def _money(amount: float) -> str:
    return f"${amount:,.2f}"


def main() -> None:
    st.set_page_config(page_title="Coffee/Tea Ordering", page_icon="☕", layout="centered")
    _ensure_data_files()
    _init_state()

    st.title("Coffee/Tea Order App")
    st.caption("Streamlit version of your terminal ordering program (employee ➝ order ➝ receipt ➝ history).")

    try:
        menu = load_menu()
    except FileNotFoundError:
        st.error(f"Missing menu file: {MENU_PATH}")
        st.stop()

    if not menu.drink_types or not menu.sizes:
        st.error("Menu is missing required categories (DRINK_TYPE / SIZES).")
        st.stop()

    st.sidebar.header("Navigation")
    step = st.sidebar.radio(
        "Step",
        ["Employee", "Order", "Review & Submit", "History"],
        index=["Employee", "Order", "Review & Submit", "History"].index(st.session_state["step"]),
    )
    st.session_state["step"] = step

    if step == "Employee":
        st.subheader("1) Employee info")

        emp_id = st.text_input("Employee ID", value=st.session_state["employee_id"]).strip()
        col1, col2 = st.columns(2)
        lookup = col1.button("Lookup / Load", use_container_width=True)
        clear = col2.button("Clear", use_container_width=True)

        if clear:
            st.session_state["employee_id"] = ""
            st.session_state["employee_record"] = None
            st.rerun()

        if lookup and emp_id:
            st.session_state["employee_id"] = emp_id
            st.session_state["employee_record"] = read_employee(emp_id)
            st.rerun()

        record = st.session_state.get("employee_record") or {}
        if emp_id and record:
            st.success("Employee found. You can edit and re-save if needed.")

        f_name = st.text_input("First name", value=str(record.get("f_name", "")))
        l_name = st.text_input("Last name", value=str(record.get("l_name", "")))
        office = st.text_input("Office to deliver to", value=str(record.get("office", "")))
        extension = st.text_input("Extension", value=str(record.get("extension", "")))
        allergies = st.text_area(
            "Allergies / sensitivities (comma-separated)",
            value=str(record.get("allergies", "")),
            height=90,
        )

        save = st.button("Save employee & continue", type="primary")
        if save:
            if not emp_id:
                st.error("Employee ID is required.")
            elif not f_name.strip() or not l_name.strip():
                st.error("First and last name are required.")
            else:
                new_record = {
                    "office": office.strip(),
                    "extension": extension.strip(),
                    "f_name": f_name.strip(),
                    "l_name": l_name.strip(),
                    "allergies": allergies.strip(),
                }
                append_employee(emp_id, new_record)
                st.session_state["employee_id"] = emp_id
                st.session_state["employee_record"] = new_record
                st.session_state["step"] = "Order"
                st.success("Saved.")
                st.rerun()

    elif step == "Order":
        st.subheader("2) Build the order")

        emp_id = st.session_state.get("employee_id", "").strip()
        emp_record = st.session_state.get("employee_record")
        if not emp_id or not emp_record:
            st.warning("Start on the Employee step first.")
            if st.button("Go to Employee"):
                st.session_state["step"] = "Employee"
                st.rerun()
            st.stop()

        drink = st.selectbox("Drink type", options=menu.drink_types)

        size_labels = [f"{size} — {_money(price)}" for size, price in zip(menu.sizes, menu.prices)]
        size_choice = st.radio("Size", options=size_labels, horizontal=True)
        size_index = size_labels.index(size_choice)
        size = menu.sizes[size_index]
        base_price = float(menu.prices[size_index])

        milk = st.selectbox("Milk", options=menu.milks or ["none"])
        flavor = st.selectbox("Flavor", options=menu.flavors or ["none"])
        pumps = st.slider("Flavor pumps ($0.10 each)", min_value=0, max_value=10, value=0, step=1)

        total = base_price + (pumps * 0.10)
        st.info(f"Total: {_money(total)}")

        save_order = st.button("Save order", type="primary")
        if save_order:
            st.session_state["order"] = {
                "drink": drink,
                "size": size,
                "milk": milk,
                "flavor": flavor,
                "pumps": pumps,
                "base_price": base_price,
                "total": total,
            }
            st.session_state["step"] = "Review & Submit"
            st.rerun()

    elif step == "Review & Submit":
        st.subheader("3) Review & submit")

        emp_id = st.session_state.get("employee_id", "").strip()
        emp_record = st.session_state.get("employee_record")
        order = st.session_state.get("order")

        if not emp_id or not emp_record:
            st.warning("Employee info is missing.")
            if st.button("Go to Employee"):
                st.session_state["step"] = "Employee"
                st.rerun()
            st.stop()
        if not order:
            st.warning("Order is missing.")
            if st.button("Go to Order"):
                st.session_state["step"] = "Order"
                st.rerun()
            st.stop()

        st.markdown("**Employee**")
        st.write(
            {
                "id": emp_id,
                "name": f"{emp_record.get('f_name','')} {emp_record.get('l_name','')}".strip(),
                "office": emp_record.get("office", ""),
                "extension": emp_record.get("extension", ""),
                "allergies": emp_record.get("allergies", ""),
            }
        )

        st.markdown("**Order**")
        st.write(
            {
                "drink": order["drink"],
                "size": order["size"],
                "milk": order["milk"],
                "flavor": order["flavor"],
                "pumps": order["pumps"],
                "total": _money(float(order["total"])),
            }
        )

        col1, col2 = st.columns(2)
        submit = col1.button("Submit order", type="primary", use_container_width=True)
        edit = col2.button("Edit order", use_container_width=True)

        if edit:
            st.session_state["step"] = "Order"
            st.rerun()

        if submit:
            now = datetime.now(timezone.utc).isoformat()
            payload = {
                "timestamp_utc": now,
                "employee_id": emp_id,
                "employee": emp_record,
                "order": order,
            }
            append_order(payload)
            st.success("Order submitted (saved to local text files on the Streamlit server).")
            st.session_state["order"] = None
            st.session_state["step"] = "History"
            st.rerun()

    else:  # History
        st.subheader("4) Order history")

        orders = read_orders()
        if not orders:
            st.info("No saved orders yet.")
            st.stop()

        emp_filter = st.text_input("Filter by employee ID (optional)").strip()
        if emp_filter:
            orders = [o for o in orders if str(o.get("employee_id", "")).strip() == emp_filter]

        st.write(f"Showing {len(orders)} order(s).")
        st.dataframe(orders, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
