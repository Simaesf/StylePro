"""
examples/dash_app.py
---------------------
Minimal Dash demo app with StylePro wired in.

Run:
    cd StylePro
    pip install -e ".[dash]"
    python examples/dash_app.py

Open http://127.0.0.1:8050 in your browser.
The StylePro FAB (floating action button) appears in the bottom-right corner.
Click it to activate canvas edit mode.
"""

import logging

import dash
from dash import dcc, html
import plotly.express as px
import pandas as pd
import numpy as np

from stylepro import DashStylePro

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dash app
# ---------------------------------------------------------------------------
app = dash.Dash(__name__, title="StylePro Dash Demo")

# ---------------------------------------------------------------------------
# StylePro integration — inject once after creating the app, before run().
# ---------------------------------------------------------------------------
sp = DashStylePro.from_config(role="admin")
sp.inject(app)

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------
_rng = np.random.default_rng(42)
df_bar = pd.DataFrame(
    {"Category": ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"],
     "Value": _rng.integers(10, 100, size=5)}
)
df_scatter = pd.DataFrame(
    {"x": _rng.standard_normal(50),
     "y": _rng.standard_normal(50),
     "size": _rng.integers(5, 25, size=50)}
)

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app.layout = html.Div(
    id="sp-root",
    children=[
        html.H1("StylePro — Dash Demo"),
        html.P("A test bed for the StylePro visual style editor."),

        html.Hr(),

        html.Div(
            style={"display": "flex", "gap": "24px"},
            children=[
                # Left column
                html.Div(
                    style={"flex": "1"},
                    children=[
                        html.H3("Bar Chart"),
                        dcc.Graph(
                            id="bar-chart",
                            figure=px.bar(df_bar, x="Category", y="Value",
                                          title="Category Values"),
                        ),
                        html.H3("Controls"),
                        dcc.Dropdown(
                            id="framework-dropdown",
                            options=[
                                {"label": "Streamlit", "value": "streamlit"},
                                {"label": "Dash", "value": "dash"},
                                {"label": "Angular", "value": "angular"},
                            ],
                            value="dash",
                            clearable=False,
                        ),
                        html.Br(),
                        dcc.Slider(
                            id="rating-slider",
                            min=1, max=10, step=1, value=7,
                            marks={i: str(i) for i in range(1, 11)},
                        ),
                    ],
                ),
                # Right column
                html.Div(
                    style={"flex": "1"},
                    children=[
                        html.H3("Scatter Plot"),
                        dcc.Graph(
                            id="scatter-chart",
                            figure=px.scatter(df_scatter, x="x", y="y",
                                              size="size", title="Scatter"),
                        ),
                        html.H3("Metrics"),
                        html.Div(
                            style={"display": "flex", "gap": "16px"},
                            children=[
                                html.Div([html.Strong("Visitors"), html.P("1,234")]),
                                html.Div([html.Strong("Revenue"), html.P("$5,678")]),
                                html.Div([html.Strong("Uptime"), html.P("99.9%")]),
                            ],
                        ),
                    ],
                ),
            ],
        ),

        html.Hr(),

        html.H3("Form"),
        html.Div([
            dcc.Input(id="email-input", type="email", placeholder="Email",
                      style={"marginRight": "8px"}),
            dcc.Textarea(id="message-input", placeholder="Message",
                         style={"display": "block", "marginTop": "8px",
                                "width": "400px"}),
            html.Button("Send", id="send-btn", n_clicks=0,
                        style={"marginTop": "8px"}),
            html.Div(id="form-output"),
        ]),
    ],
    style={"fontFamily": "system-ui, sans-serif", "padding": "24px"},
)


if __name__ == "__main__":
    log.info("Starting StylePro Dash demo on http://127.0.0.1:8050")
    app.run(debug=True)
