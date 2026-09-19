"""Cay ngoai le va bang ma loi.

Moi loi co: ma on dinh (`code`), thong bao tieng Viet cho nguoi dung
(`message_vi`), va ma HTTP tuong ung. Nho vay frontend xu ly duoc theo `code`
thay vi so khop chuoi, va thong bao doi duoc ma khong pha frontend.

QUY TAC:
  - Khong bao gio `raise Exception(...)` tran. Luon dung mot lop trong day.
  - `message_vi` la thu NGUOI DUNG doc. Khong dua ten bang, ten cot, stack trace
    vao do - nhung thu do di vao `detail` va chi ra log.
  - Them loi moi: them lop + dang ky trong ERROR_CATALOG o cuoi file.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Goc cua moi loi trong ung dung."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    message_vi: str = "Đã có lỗi xảy ra."
    retryable: bool = False

    def __init__(self, detail: str = "", **context: Any) -> None:
        self.detail = detail
        self.context = context
        super().__init__(f"{self.code}: {detail}" if detail else self.code)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message_vi,
            "detail": self.detail,
            "retryable": self.retryable,
            "context": self.context,
        }


# =============================================================================
# CAU HINH  (4xx cho nguoi van hanh, phat hien luc khoi dong)
# =============================================================================

class ConfigError(AppError):
    code = "CONFIG_ERROR"
    http_status = 500
    message_vi = "Cấu hình hệ thống không hợp lệ."


class MissingSecretError(ConfigError):
    code = "MISSING_SECRET"
    message_vi = "Thiếu thông tin cấu hình bắt buộc."


class CatalogValidationError(ConfigError):
    code = "CATALOG_INVALID"
    message_vi = "Catalog chỉ số không khớp với cấu trúc dữ liệu thật."


class PromptValidationError(ConfigError):
    code = "PROMPT_INVALID"
    message_vi = "File prompt không hợp lệ."


# =============================================================================
# DU LIEU
# =============================================================================

class DataError(AppError):
    code = "DATA_ERROR"
    http_status = 503
    message_vi = "Không truy cập được dữ liệu."


class DatabaseUnavailable(DataError):
    code = "DB_UNAVAILABLE"
    message_vi = "Đang mất kết nối tới cơ sở dữ liệu."
    retryable = True


class ReadOnlyViolation(DataError):
    """Agent co gang ghi du lieu. Day la LOI LAP TRINH, khong phai loi nguoi dung.

    Neu loi nay xuat hien, nghia la mot truy van ghi da lot qua moi lop kiem tra
    va chi bi chan o muc database. Phai dieu tra ngay.
    """
    code = "READ_ONLY_VIOLATION"
    http_status = 500
    message_vi = "Thao tác không được phép."


class DataQualityBlocked(DataError):
    code = "DQ_BLOCKED"
    message_vi = "Dữ liệu chưa qua kiểm tra chất lượng nên tạm dừng trả lời."


class QueryTimeout(DataError):
    code = "QUERY_TIMEOUT"
    http_status = 504
    message_vi = "Truy vấn chạy quá lâu và đã bị dừng."
    retryable = True


# =============================================================================
# SEMANTIC LAYER  (phan lon la loi cua LLM, bat truoc khi cham database)
# =============================================================================

class SemanticError(AppError):
    code = "SEMANTIC_ERROR"
    http_status = 400
    message_vi = "Không hiểu được yêu cầu truy vấn."


class UnknownMetricError(SemanticError):
    code = "UNKNOWN_METRIC"
    message_vi = "Chưa có định nghĩa cho chỉ số này."


class UnknownDimensionError(SemanticError):
    code = "UNKNOWN_DIMENSION"
    message_vi = "Chưa có định nghĩa cho chiều phân tích này."


class InvalidFilterError(SemanticError):
    code = "INVALID_FILTER"
    message_vi = "Điều kiện lọc không hợp lệ."


class DimensionNotAllowedError(SemanticError):
    code = "DIMENSION_NOT_ALLOWED"
    message_vi = "Chỉ số này không cắt được theo chiều đó."


class ForbiddenMetricError(SemanticError):
    """Chi so bi CAM vi du lieu khong cho phep tinh, vi du so sanh lien thang."""
    code = "FORBIDDEN_METRIC"
    message_vi = "Dữ liệu hiện có không cho phép tính chỉ số này."


class InsufficientHistoryError(SemanticError):
    code = "INSUFFICIENT_HISTORY"
    message_vi = "Dữ liệu giao dịch chỉ có từ 01/08/2026 đến 31/08/2026."


class InsufficientSampleError(SemanticError):
    code = "INSUFFICIENT_SAMPLE"
    message_vi = "Cỡ mẫu quá nhỏ để kết luận."


# =============================================================================
# SQL GUARD  (lop L0/L1)
# =============================================================================

class SQLGuardError(AppError):
    code = "SQL_GUARD_ERROR"
    http_status = 400
    message_vi = "Truy vấn không vượt qua kiểm tra an toàn."


class SQLParseError(SQLGuardError):
    code = "SQL_PARSE_ERROR"
    message_vi = "Không phân tích được cú pháp truy vấn."


class SQLForbiddenStatement(SQLGuardError):
    code = "SQL_FORBIDDEN"
    message_vi = "Truy vấn chứa lệnh không được phép."


class SQLUnboundIdentifier(SQLGuardError):
    """Bang hoac cot khong ton tai. Day la hallucination schema dien hinh."""
    code = "SQL_UNBOUND_IDENTIFIER"
    message_vi = "Truy vấn tham chiếu bảng hoặc cột không tồn tại."


class SQLSchemaNotAllowed(SQLGuardError):
    code = "SQL_SCHEMA_NOT_ALLOWED"
    message_vi = "Truy vấn chạm tới vùng dữ liệu không được phép."


class SQLRepairExhausted(SQLGuardError):
    code = "SQL_REPAIR_EXHAUSTED"
    message_vi = "Không dựng được truy vấn cho câu hỏi này."


# =============================================================================
# KIEM CHUNG  (lop L2-L6)
# =============================================================================

class VerificationError(AppError):
    code = "VERIFICATION_ERROR"
    http_status = 200      # KHONG phai loi HTTP: cau tra loi van tra ve, nhung bi chan phan dien giai
    message_vi = "Câu trả lời không vượt qua kiểm chứng."


class NumericUngrounded(VerificationError):
    code = "NUMERIC_UNGROUNDED"
    message_vi = "Một số con số trong câu trả lời không đối chiếu được với dữ liệu nguồn."


class EntityUngrounded(VerificationError):
    code = "ENTITY_UNGROUNDED"
    message_vi = "Câu trả lời nhắc tới đối tượng không có trong dữ liệu."


class UnsupportedComparison(VerificationError):
    code = "UNSUPPORTED_COMPARISON"
    message_vi = "Câu trả lời so sánh hai nhóm mà chênh lệch nằm trong sai số thống kê."


class UnsupportedCausalClaim(VerificationError):
    code = "UNSUPPORTED_CAUSAL_CLAIM"
    message_vi = "Câu trả lời suy luận nhân quả trong khi dữ liệu chỉ cho thấy tương quan."


class JudgeContradiction(VerificationError):
    code = "JUDGE_CONTRADICTION"
    message_vi = "Kiểm tra lại phát hiện phát biểu mâu thuẫn với dữ liệu."


class LowConsistency(VerificationError):
    code = "LOW_CONSISTENCY"
    message_vi = "Có nhiều cách hiểu câu hỏi cho kết quả khác nhau."


# =============================================================================
# LLM
# =============================================================================

class LLMError(AppError):
    code = "LLM_ERROR"
    http_status = 503
    message_vi = "Mô hình tạm không phản hồi."
    retryable = True


class LLMRateLimited(LLMError):
    code = "LLM_RATE_LIMITED"
    http_status = 429
    message_vi = "Đang chờ lượt gọi mô hình."
    retryable = True


class LLMTimeout(LLMError):
    code = "LLM_TIMEOUT"
    http_status = 504
    message_vi = "Mô hình phản hồi quá chậm."
    retryable = True


class LLMUnavailable(LLMError):
    """Het luot thu lai. Orchestrator chuyen sang che do template."""
    code = "LLM_UNAVAILABLE"
    message_vi = "Mô hình tạm không phản hồi — hiển thị số liệu dạng rút gọn."
    retryable = False


class LLMBudgetExceeded(LLMError):
    code = "LLM_BUDGET_EXCEEDED"
    http_status = 429
    message_vi = "Câu hỏi này cần quá nhiều lượt gọi mô hình."
    retryable = False


# =============================================================================
# AGENT
# =============================================================================

class AgentError(AppError):
    code = "AGENT_ERROR"
    http_status = 500
    message_vi = "Không xử lý được câu hỏi."


class PlaybookNotFound(AgentError):
    code = "PLAYBOOK_NOT_FOUND"
    message_vi = "Chưa có quy trình phân tích cho loại câu hỏi này."


class MissingEntityError(AgentError):
    code = "MISSING_ENTITY"
    http_status = 400
    message_vi = "Cần biết thêm thông tin để trả lời."


class OutOfScopeError(AgentError):
    code = "OUT_OF_SCOPE"
    http_status = 200
    message_vi = "Câu hỏi nằm ngoài phạm vi dữ liệu chiến dịch."


# =============================================================================
# BANG MA LOI  - frontend va tai lieu doc tu day
# =============================================================================

ERROR_CATALOG: dict[str, type[AppError]] = {
    cls.code: cls
    for cls in [
        AppError,
        ConfigError, MissingSecretError, CatalogValidationError, PromptValidationError,
        DataError, DatabaseUnavailable, ReadOnlyViolation, DataQualityBlocked, QueryTimeout,
        SemanticError, UnknownMetricError, UnknownDimensionError, InvalidFilterError,
        DimensionNotAllowedError, ForbiddenMetricError, InsufficientHistoryError,
        InsufficientSampleError,
        SQLGuardError, SQLParseError, SQLForbiddenStatement, SQLUnboundIdentifier,
        SQLSchemaNotAllowed, SQLRepairExhausted,
        VerificationError, NumericUngrounded, EntityUngrounded, UnsupportedComparison,
        UnsupportedCausalClaim, JudgeContradiction, LowConsistency,
        LLMError, LLMRateLimited, LLMTimeout, LLMUnavailable, LLMBudgetExceeded,
        AgentError, PlaybookNotFound, MissingEntityError, OutOfScopeError,
    ]
}


def describe_catalog() -> list[dict[str, object]]:
    """Dung cho GET /api/admin/errors va cho tai lieu."""
    return [
        {"code": c, "http_status": k.http_status,
         "message_vi": k.message_vi, "retryable": k.retryable}
        for c, k in sorted(ERROR_CATALOG.items())
    ]
