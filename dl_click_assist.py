#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""向后兼容入口：python dl_click_assist.py → main.main()"""

from main import main

if __name__ == "__main__":
    raise SystemExit(main())
