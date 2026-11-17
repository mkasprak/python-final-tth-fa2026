# Python Final Project (Streamlit)

This repo contains a Streamlit web app version of the `final_project/` coffee/tea ordering program.

## Run locally

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Notes about saving

- Employee records are appended to `final_project/employee.txt`.
- Orders are appended (as JSON lines) to `final_project/order_history.txt`.
- On Streamlit Community Cloud, local file storage is **ephemeral** (it can reset when the app restarts).

## Admin-only history

The **History** page is password protected. Configure one of:

- Streamlit Secrets: set `admin_password`
- Environment variable: `ADMIN_PASSWORD`
