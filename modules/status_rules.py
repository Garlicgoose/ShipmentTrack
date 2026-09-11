# -*- coding: utf-8 -*-
"""承运商状态的严格标准化与匹配。"""
import re


def normalize_status(value):
    text = str(value or "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" .,:;：；。！？!?-—|\t\r\n").casefold()


def matches_exact_status(status, default_statuses=(), custom_statuses=()):
    current = normalize_status(status)
    if not current:
        return False
    accepted = {
        normalize_status(value)
        for value in (*tuple(default_statuses), *tuple(custom_statuses))
        if normalize_status(value)
    }
    return current in accepted
