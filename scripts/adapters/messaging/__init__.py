"""Messaging adapter family — Outlook email + Teams chat sends.

One module per provider (currently m365 via the mgc Graph CLI), conforming to
_contract.MessagingAdapter. Selected via profile integrations.yaml
(messaging.provider) and reached only through the Tier-2 adapters.publish gate.
"""
