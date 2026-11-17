from __future__ import annotations

import ast
import json
import os
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


def get_admin_password() -> Optional[str]:
    admin_password = None
    try:
        admin_password = st.secrets.get("admin_password")  # type: ignore[attr-defined]
    except Exception:
        admin_password = None
    return admin_password or os.environ.get("ADMIN_PASSWORD")


def _money(amount: float) -> str:
    return f"${amount:,.2f}"


def _parse_ts(ts: Any) -> Optional[datetime]:
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _format_ts(ts: Any) -> str:
    dt = _parse_ts(ts)
    if not dt:
        return "Unknown time"
    local = dt.astimezone()
    return local.strftime("%b %d, %Y • %I:%M %p").replace(" 0", " ")


def _order_breakdown(order: dict[str, Any]) -> dict[str, Any]:
    base_price = float(order.get("base_price", 0.0) or 0.0)
    pumps = int(order.get("pumps", 0) or 0)
    pump_cost = pumps * 0.10
    total = float(order.get("total", base_price + pump_cost) or 0.0)
    return {"base_price": base_price, "pumps": pumps, "pump_cost": pump_cost, "total": total}


def _to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    import csv
    import io

    buf = io.StringIO()
    fieldnames: list[str] = sorted({k for r in rows for k in r.keys()})
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


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

    admin_password = get_admin_password()

    st.sidebar.header("Navigation")
    steps = ["Employee", "Order", "Review & Submit", "My Orders"]
    if admin_password:
        steps.append("Admin History")
    step = st.sidebar.radio(
        "Step",
        steps,
        index=steps.index(st.session_state["step"]) if st.session_state["step"] in steps else 0,
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

        employee_name = f"{emp_record.get('f_name','')} {emp_record.get('l_name','')}".strip()
        allergies = str(emp_record.get("allergies", "") or "").strip()
        breakdown = _order_breakdown(order)

        st.progress(0.75, text="Almost done — review your receipt and submit.")

        top_left, top_right = st.columns([2, 1], gap="large")
        with top_left:
            st.markdown("#### Receipt")
            st.caption("Double-check everything looks right before submitting.")
            st.markdown(
                f"""
**Drink:** {order.get('drink','')}

**Size:** {order.get('size','')}  •  **Milk:** {order.get('milk','')}  •  **Flavor:** {order.get('flavor','')}

**Pumps:** {breakdown['pumps']}  (+{_money(float(breakdown['pump_cost']))})
                """.strip()
            )

        with top_right:
            st.markdown("#### Total")
            st.metric("Amount due", _money(float(breakdown["total"])))
            st.caption(f"Base: {_money(float(breakdown['base_price']))}")

        st.divider()

        details_left, details_right = st.columns(2, gap="large")
        with details_left:
            st.markdown("#### For")
            st.markdown(
                f"""
**Employee ID:** `{emp_id}`

**Name:** {employee_name or "—"}
                """.strip()
            )
            if allergies:
                st.warning(f"Allergies / sensitivities: {allergies}", icon="⚠️")

        with details_right:
            st.markdown("#### Deliver to")
            office = str(emp_record.get("office", "") or "").strip() or "—"
            extension = str(emp_record.get("extension", "") or "").strip() or "—"
            st.markdown(
                f"""
**Office:** {office}

**Extension:** {extension}
                """.strip()
            )

        # Note: widgets inside a form only update their values on submit, so a checkbox
        # cannot be used to "enable" the submit button within the same form.
        confirm = st.checkbox("I confirm the employee info and order details are correct.")
        b1, b2, _ = st.columns([1, 1, 2])
        edit = b1.button("Edit order", use_container_width=True)
        submit = b2.button(
            "Submit order",
            type="primary",
            use_container_width=True,
            disabled=not confirm,
        )

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
            st.success("Submitted. Your order is now saved and visible in My Orders.")
            st.session_state["order"] = None
            st.session_state["step"] = "My Orders"
            st.rerun()

    elif step == "My Orders":
        st.subheader("4) My orders")

        emp_id = st.session_state.get("employee_id", "").strip()
        if not emp_id:
            st.warning("Enter/lookup your Employee ID first.")
            if st.button("Go to Employee"):
                st.session_state["step"] = "Employee"
                st.rerun()
            st.stop()

        orders = [o for o in read_orders() if str(o.get("employee_id", "")).strip() == emp_id]
        if not orders:
            st.info("No saved orders for this Employee ID yet.")
            st.stop()

        orders = sorted(orders, key=lambda o: _parse_ts(o.get("timestamp_utc")) or datetime.min, reverse=True)

        header_left, header_right = st.columns([2, 1])
        with header_left:
            st.caption(f"Signed in as Employee ID `{emp_id}`")
        with header_right:
            if st.button("Start a new order", type="primary", use_container_width=True):
                st.session_state["step"] = "Order"
                st.rerun()

        st.divider()

        max_show = st.slider(
            "Show most recent orders",
            min_value=1,
            max_value=min(50, len(orders)),
            value=min(10, len(orders)),
        )
        shown = orders[:max_show]

        for idx, entry in enumerate(shown, start=1):
            order_data = entry.get("order") if isinstance(entry.get("order"), dict) else {}
            order_data = order_data if isinstance(order_data, dict) else {}
            breakdown = _order_breakdown(order_data)
            title = f"{idx}. {_format_ts(entry.get('timestamp_utc'))} • {_money(float(breakdown['total']))}"
            with st.expander(title, expanded=(idx == 1)):
                c1, c2, c3 = st.columns([2, 1, 1], gap="large")
                with c1:
                    st.markdown("**Order**")
                    st.write(
                        {
                            "drink": order_data.get("drink", ""),
                            "size": order_data.get("size", ""),
                            "milk": order_data.get("milk", ""),
                            "flavor": order_data.get("flavor", ""),
                            "pumps": order_data.get("pumps", 0),
                        }
                    )
                with c2:
                    st.markdown("**Pricing**")
                    st.metric("Total", _money(float(breakdown["total"])))
                    st.caption(f"Base: {_money(float(breakdown['base_price']))}")
                    st.caption(f"Pumps: {_money(float(breakdown['pump_cost']))}")
                with c3:
                    st.markdown("**Actions**")
                    st.download_button(
                        "Download JSON",
                        data=json.dumps(entry, ensure_ascii=False, indent=2),
                        file_name=f"order_{emp_id}_{idx}.json",
                        mime="application/json",
                        use_container_width=True,
                    )

        st.divider()
        st.markdown("#### Download / table view")
        flat_rows: list[dict[str, Any]] = []
        for entry in orders:
            o = entry.get("order") if isinstance(entry.get("order"), dict) else {}
            o = o if isinstance(o, dict) else {}
            flat_rows.append(
                {
                    "timestamp_utc": entry.get("timestamp_utc"),
                    "employee_id": entry.get("employee_id"),
                    "drink": o.get("drink"),
                    "size": o.get("size"),
                    "milk": o.get("milk"),
                    "flavor": o.get("flavor"),
                    "pumps": o.get("pumps"),
                    "base_price": o.get("base_price"),
                    "total": o.get("total"),
                }
            )

        st.download_button(
            "Download my orders (CSV)",
            data=_to_csv(flat_rows),
            file_name=f"my_orders_{emp_id}.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.dataframe(flat_rows[:max_show], use_container_width=True, hide_index=True)

    else:  # Admin History
        st.subheader("Admin history")

        if not admin_password:
            st.error(
                "Admin history is not configured. Set `admin_password` in Streamlit Secrets "
                "(recommended) or `ADMIN_PASSWORD` env var."
            )
            st.stop()

        entered = st.text_input("Admin password", type="password")
        if entered != admin_password:
            st.info("Enter the admin password to view admin history.")
            st.stop()

        orders = read_orders()
        if not orders:
            st.info("No saved orders yet.")
            st.stop()

        st.write(f"Showing {len(orders)} order(s).")
        st.dataframe(orders, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
