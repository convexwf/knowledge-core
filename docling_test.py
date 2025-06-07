# !/usr/bin/python3
# -*- coding: utf-8 -*-
# @Project : knowledge-core
# @FileName : docling_test.py
# @Author : convexwf@gmail.com
# @CreateDate : 2025-06-07 16:46
# @UpdateTime : 2025-06-07 16:46

from docling.document_converter import DocumentConverter

source = "https://arxiv.org/pdf/2408.09869"  # document per local path or URL
# source = "https://book-refactoring2.ifmicro.com/docs/ch2.html"
converter = DocumentConverter()
result = converter.convert(source)
# print(
#     result.document.export_to_markdown()
# )  # output: "## Docling Technical Report[...]"

with open("out.md", "w+", encoding="utf-8") as f:
    f.write(result.document.export_to_markdown(image_mode="referenced"))
