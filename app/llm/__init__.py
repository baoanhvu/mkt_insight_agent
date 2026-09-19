"""Goi LLM. Khong biet gi ve nghiep vu - chi la `app.contracts.LLMClient`.

Token bucket dat o CLIENT (khong dua vao bat loi 429 cua provider): tran MaaS
la 10 RPM tinh CHUNG ca tai khoan, nen neu de dung tran moi lui thi nhieu
request dong thoi se cung lui mot luc va tao hieu ung bay dan. Xem
docs/10-config-secrets.md muc "MaaS gioi han 10 request/phut".
"""
