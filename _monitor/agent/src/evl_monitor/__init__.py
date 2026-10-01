"""EVL server monitor agent.

Samples host and GPU metrics, keeps space-bounded history in SQLite, and serves
prebuilt JSON files over HTTP. The public page at www.evl.uic.edu/monitor reads
them through the web server's nginx.
"""

__version__ = "1.0.0"
