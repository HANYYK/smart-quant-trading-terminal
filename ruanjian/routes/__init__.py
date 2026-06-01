"""Route package.

Blueprints are imported explicitly in app.create_app to avoid loading optional
market-data dependencies when only a subset of routes is needed.
"""
