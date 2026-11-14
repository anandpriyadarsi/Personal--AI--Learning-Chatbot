"""Explicit pytest plugin; no shared conftest changes or global user settings."""
import os
import pytest


@pytest.fixture(autouse=True)
def offline_browser_proxy(monkeypatch):
    if os.environ.get('ANVAYA_OFFLINE_GUARD')!='1':return
    try:from playwright.sync_api import BrowserType
    except ImportError:return
    original=BrowserType.launch
    def launch(self,*args,**kwargs):
        # Chromium cannot send provider requests, even with direct numeric URLs.
        # Loopback Flask fixtures remain reachable. No remote proxy is contacted.
        kwargs['proxy']={'server':'http://127.0.0.1:9','bypass':'localhost,127.0.0.1,[::1]'}
        kwargs['args']=[*kwargs.get('args',[]),'--disable-background-networking','--disable-component-update']
        kwargs.setdefault('timeout',30000)
        return original(self,*args,**kwargs)
    monkeypatch.setattr(BrowserType,'launch',launch)
