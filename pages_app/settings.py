import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime
import io
import copy
import json

# ─────────────────────────────────────────────────────────────────────────────
# MAIN PAGE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class SettingsPage:
    def __init__(self, df_all: pd.DataFrame, current_user: str = 'Operator'):
        self.df_all = df_all
        self.current_user = current_user