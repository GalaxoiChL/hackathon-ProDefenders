"""Advertiser outreach: find regional businesses, invite them by email to bid on in-video ad placements.

  sources.py   where businesses come from (OpenStreetMap; Brave Search if a key is set)
  crawl.py     reads the business's own website for a public contact email + description
  llm.py       local AI (Ollama) with deterministic fallbacks
  leads.py     search -> enrich -> AI qualification
  mailer.py    AI-written email in the local language, compliance footer, outbox / SMTP
  bids.py      placements (clip x market), floor prices, signed bid links, bids
  routes.py    /api/outreach/..., /api/placements, /api/bids, /bid/<token>
"""
