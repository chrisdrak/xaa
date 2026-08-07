#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Σημείο εκκίνησης για το APK.

Το `flet build` ψάχνει από προεπιλογή module με όνομα "main".
Όλη η εφαρμογή είναι στο xa_flet.py / xa_core.py.
"""

import xa_flet

if __name__ == "__main__":
    xa_flet.run_app(xa_flet.main)
