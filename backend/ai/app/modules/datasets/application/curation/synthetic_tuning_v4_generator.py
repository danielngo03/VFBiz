from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from app.modules.datasets.application.curation.synthetic_tuning_candidate import (
    count_words,
    digest,
)

_CANDIDATE_ID = "vivi-behavior-synthetic-v4"
_WORK_ITEM = "VFBIZ-0214"
_RUN_ID = "vivi-behavior-synthetic-v4-run-001"
_GENERATOR_IDENTITY = "vfbiz-synthetic-behavior-composer@4.0.0"
_SEED_SET_ID = "synthetic-behavior-seeds-v4"
_SYSTEM_INSTRUCTION = (
    "Bạn là trợ lý hỗ trợ bằng tiếng Việt. Trả lời tự nhiên, ngắn gọn, "
    "minh bạch về giới hạn; không tự tạo dữ kiện hoặc nói rằng một hành động "
    "đã hoàn tất khi chưa có bằng chứng."
)
_REGRESSION_SOURCES: tuple[tuple[str, str, int], ...] = (
    (
        "vivi-behavior-synthetic-v2-fam-05-21-v5",
        "0d81fbb247294d66dfb4b7a080eb228905278247a74acf121af628c26db6c575",
        20,
    ),
    (
        "vivi-behavior-synthetic-v2-fam-05-22-v5",
        "4e267af43f69b4a482e468b5190cc25c282fb7f5d419c7b2f1b944d8e83ef62d",
        20,
    ),
    (
        "vivi-behavior-synthetic-v2-fam-05-23-v5",
        "76e1b4bd3db6500259a3b398005cb9d6180923bd8737e105204afd3a178c5840",
        20,
    ),
    (
        "vivi-behavior-synthetic-v2-fam-05-24-v5",
        "234b26a33c16a6458c002f53aa9c916910604980499d1df3dbd82295c0e80d2a",
        22,
    ),
)

_OPENINGS = (
    "Mình cần hỗ trợ việc này:",
    "Bạn giúp mình xử lý tình huống sau nhé:",
    "Mình đang hơi lúng túng vì",
    "Cho mình một cách giải quyết rõ ràng:",
    "Mình muốn làm đúng ngay từ đầu:",
)

_RESPONSE_LEADS: Mapping[str, tuple[str, ...]] = {
    "concise_structure": (
        "Cách ngắn gọn nhất là",
        "Bạn có thể xử lý theo hai phần:",
        "Mình đề xuất bắt đầu từ",
        "Để dễ theo dõi, hãy",
        "Một cách rõ ràng là",
    ),
    "clarification": (
        "Để hỗ trợ đúng trọng tâm,",
        "Mình cần làm rõ một điểm:",
        "Trước khi đề xuất cách làm,",
        "Để tránh hiểu sai yêu cầu,",
        "Bạn bổ sung giúp mình điều này:",
    ),
    "refusal_handoff": (
        "Mình chưa thể thực hiện thay bạn.",
        "Việc đó cần người có thẩm quyền xác nhận.",
        "Mình không thể tự hoàn tất hành động này.",
        "Yêu cầu này cần được chuyển đúng người xử lý.",
        "Mình chỉ có thể hỗ trợ chuẩn bị, không thể tự phê duyệt.",
    ),
    "citation_transparency": (
        "Mình cần nguồn và ngày hiệu lực trước khi kết luận.",
        "Thông tin này chỉ nên trả lời khi có tài liệu còn hiệu lực.",
        "Mình chưa thể xác nhận nếu thiếu nguồn kiểm chứng.",
        "Trước hết cần đối chiếu đúng phiên bản tài liệu.",
        "Mình sẽ không đoán khi chưa có bằng chứng phù hợp.",
    ),
    "state_transparency": (
        "Mình chưa thực hiện hành động đó.",
        "Hiện chưa có biên nhận xác nhận hoàn tất.",
        "Trạng thái lúc này vẫn là chưa thực hiện.",
        "Mình mới có thể chuẩn bị nội dung, chưa thể gửi thay bạn.",
        "Chưa có bằng chứng cho thấy yêu cầu đã hoàn tất.",
    ),
}


@dataclass(frozen=True, slots=True)
class FamilySpec:
    family_id: str
    split: str
    behavior: str
    subject: str
    anchor: str
    requests: tuple[str, str, str, str, str]
    responses: tuple[str, str, str, str, str]


@dataclass(frozen=True, slots=True)
class GeneratedCandidate:
    records: tuple[dict[str, Any], ...]
    family_lock: dict[str, Any]
    pinned_revisions: dict[str, Any]
    regression_manifest: dict[str, Any]


_FAMILIES: tuple[FamilySpec, ...] = (
    FamilySpec(
        "clear-next-step",
        "train",
        "concise_structure",
        "bước tiếp theo",
        "bước tiếp theo",
        (
            "mình có nhiều ghi chú nhưng chưa biết bắt đầu từ đâu",
            "mình muốn chốt việc cần làm trước khi trao đổi",
            "mình cần biến một yêu cầu dài thành hành động cụ thể",
            "mình muốn sắp xếp việc nào làm trước, việc nào làm sau",
            "mình cần một hướng đi ngắn gọn để không bỏ sót",
        ),
        (
            "xác định mục tiêu chính rồi ghi một hành động kế tiếp",
            "chọn việc cần xác nhận trước và ghi rõ người phụ trách",
            "tách yêu cầu thành điều đã biết và điều còn phải hỏi",
            "xếp các việc theo phụ thuộc rồi chốt mốc kiểm tra",
            "ghi ba đầu việc thiết yếu và bỏ phần chưa cần thiết",
        ),
    ),
    FamilySpec(
        "support-checklist",
        "train",
        "concise_structure",
        "danh sách chuẩn bị",
        "danh sách chuẩn bị",
        (
            "mình sắp trao đổi với bộ phận hỗ trợ",
            "mình muốn chuẩn bị trước một cuộc gọi",
            "mình cần gửi yêu cầu sao cho dễ hiểu",
            "mình muốn bàn giao tình huống cho đồng nghiệp",
            "mình cần rà lại thông tin trước khi nhờ hỗ trợ",
        ),
        (
            "ghi mục tiêu, bối cảnh và kết quả mong muốn",
            "chuẩn bị câu hỏi chính, mốc thời gian và tài liệu liên quan",
            "nêu vấn đề, ảnh hưởng và điều cần xác nhận",
            "tóm tắt việc đã làm, việc còn mở và người nhận",
            "kiểm tra nguồn, thời điểm và thông tin còn thiếu",
        ),
    ),
    FamilySpec(
        "short-summary",
        "train",
        "concise_structure",
        "bản tóm tắt",
        "bản tóm tắt",
        (
            "mình có một đoạn giải thích quá dài",
            "mình muốn rút gọn nội dung bàn giao",
            "mình cần tóm tắt một cuộc trao đổi",
            "mình muốn ghi lại quyết định vừa thống nhất",
            "mình cần một ghi chú dễ đọc lại",
        ),
        (
            "giữ lại mục tiêu, quyết định và việc tiếp theo",
            "nêu bối cảnh trong một câu rồi liệt kê đầu việc",
            "ghi điều đã xác nhận, điều chưa rõ và mốc tiếp theo",
            "tách quyết định khỏi giả định và ghi người chịu trách nhiệm",
            "dùng tiêu đề ngắn rồi thêm tối đa ba ý chính",
        ),
    ),
    FamilySpec(
        "review-order",
        "train",
        "concise_structure",
        "thứ tự kiểm tra",
        "thứ tự kiểm tra",
        (
            "mình chưa biết nên kiểm tra phần nào trước",
            "mình có nhiều dấu hiệu cần xem lại",
            "mình muốn tránh sửa nhầm nguyên nhân",
            "mình cần một trình tự rà soát có thể lặp lại",
            "mình muốn biết khi nào nên dừng và chuyển người khác",
        ),
        (
            "kiểm tra điều kiện đầu vào trước rồi mới xem kết quả",
            "xác nhận dữ kiện quan sát được trước các giả thuyết",
            "thử thay đổi nhỏ, đo lại rồi mới kết luận",
            "ghi từng bước, kết quả và điểm khác biệt",
            "dừng khi thiếu quyền hoặc bằng chứng và chuyển đúng người",
        ),
    ),
    FamilySpec(
        "ambiguous-document",
        "train",
        "clarification",
        "tài liệu cần xem",
        "tài liệu",
        (
            "mình muốn xem lại tài liệu gần đây",
            "mình cần tìm bản hướng dẫn phù hợp",
            "mình muốn đối chiếu một nội dung đã đọc",
            "mình cần bản đang được áp dụng",
            "mình muốn lấy đúng tệp để trao đổi",
        ),
        (
            "bạn đang tìm loại tài liệu nào và dùng cho mục đích gì",
            "bạn nhớ chủ đề hoặc đơn vị phát hành không",
            "bạn cần đối chiếu phần nào trong nội dung đó",
            "bạn có mốc thời gian hoặc phiên bản cần dùng không",
            "bạn biết tên gần đúng hoặc người đã gửi tệp không",
        ),
    ),
    FamilySpec(
        "ambiguous-request",
        "train",
        "clarification",
        "yêu cầu hỗ trợ",
        "yêu cầu",
        (
            "mình cần hỗ trợ gấp nhưng chưa biết diễn đạt",
            "mình muốn nhờ xử lý một việc",
            "mình có vấn đề nhưng chưa rõ thuộc nhóm nào",
            "mình chưa biết bộ phận nào nên tiếp nhận việc này",
            "mình cần biết nên mô tả tình huống ra sao",
        ),
        (
            "kết quả bạn muốn nhận được là gì",
            "việc nào bạn muốn được xử lý trước",
            "vấn đề ảnh hưởng tới ai hoặc quy trình nào",
            "bạn mong bộ phận tiếp nhận phản hồi hoặc thực hiện điều gì",
            "bạn đã thử bước nào và nhận kết quả gì",
        ),
    ),
    FamilySpec(
        "ambiguous-comparison",
        "train",
        "clarification",
        "tiêu chí so sánh",
        "tiêu chí",
        (
            "mình muốn biết lựa chọn nào phù hợp hơn",
            "mình đang cân nhắc hai phương án",
            "mình cần so sánh nhưng có quá nhiều yếu tố",
            "mình muốn quyết định mà không bỏ sót điều quan trọng",
            "mình chưa biết nên ưu tiên điều gì",
        ),
        (
            "bạn ưu tiên chi phí, thời gian hay mức độ thuận tiện",
            "mục tiêu sử dụng và giới hạn chính của bạn là gì",
            "tiêu chí nào là bắt buộc và tiêu chí nào có thể đánh đổi",
            "bạn muốn so sánh trong khoảng thời gian nào",
            "điều gì sẽ khiến một phương án bị loại ngay",
        ),
    ),
    FamilySpec(
        "ambiguous-time",
        "train",
        "clarification",
        "mốc thời gian",
        "thời gian",
        (
            "mình muốn việc này hoàn thành sớm",
            "mình cần biết khi nào nên theo dõi lại",
            "mình muốn lên lịch nhưng chưa chốt ngày",
            "mình cần một hạn xử lý hợp lý",
            "mình muốn tránh để yêu cầu bị quên",
        ),
        (
            "hạn cuối thực tế của bạn là khi nào",
            "bạn đã có mã hoặc thời điểm gửi yêu cầu chưa",
            "khung giờ nào phù hợp và có ràng buộc nào không",
            "việc này phụ thuộc vào phản hồi của ai",
            "sau bao lâu không có phản hồi thì cần chuyển cấp",
        ),
    ),
    FamilySpec(
        "no-self-approval",
        "train",
        "refusal_handoff",
        "phê duyệt nội dung",
        "phê duyệt",
        (
            "mình muốn bạn duyệt luôn nội dung này",
            "mình cần bỏ qua bước kiểm tra của người phụ trách",
            "mình muốn coi bản nháp là đã được chấp nhận",
            "mình cần xác nhận thay cho người có thẩm quyền",
            "mình muốn phát hành ngay dù chưa có chữ ký",
        ),
        (
            "chuẩn bị bản tóm tắt thay đổi để người phụ trách xem",
            "liệt kê phần cần quyết định và bằng chứng đi kèm",
            "đánh dấu rõ đây vẫn là bản nháp chờ xem xét",
            "soạn gói bàn giao để người đúng vai trò xác nhận",
            "kiểm tra đủ người duyệt rồi mới chuyển trạng thái",
        ),
    ),
    FamilySpec(
        "no-account-change",
        "train",
        "refusal_handoff",
        "thay đổi quyền truy cập",
        "quyền truy cập",
        (
            "mình muốn bạn cấp thêm quyền ngay",
            "mình cần đổi vai trò của một tài khoản",
            "mình muốn mở quyền mà không cần xác nhận",
            "mình cần truy cập thay cho người khác",
            "mình muốn bỏ giới hạn hiện tại",
        ),
        (
            "ghi rõ quyền cần có và lý do sử dụng",
            "chuyển yêu cầu tới người quản lý quyền phù hợp",
            "chuẩn bị bằng chứng nghiệp vụ trước khi xin thay đổi",
            "xác minh danh tính và phạm vi trước khi xử lý",
            "đề xuất quyền tối thiểu thay vì mở rộng toàn bộ",
        ),
    ),
    FamilySpec(
        "no-send-action",
        "train",
        "refusal_handoff",
        "gửi yêu cầu",
        "gửi yêu cầu",
        (
            "mình muốn bạn gửi thay ngay bây giờ",
            "mình cần chuyển nội dung này cho bên khác",
            "mình muốn coi như yêu cầu đã được gửi",
            "mình cần bạn xác nhận người nhận thay mình",
            "mình muốn bỏ qua bước xem lại trước khi gửi",
        ),
        (
            "soạn bản nháp để bạn kiểm tra trước",
            "chuẩn bị người nhận, tiêu đề và nội dung bàn giao",
            "giữ trạng thái bản nháp cho tới khi có biên nhận",
            "xác nhận kênh và người nhận với bạn trước",
            "đưa ra danh sách kiểm tra cuối để bạn chủ động gửi",
        ),
    ),
    FamilySpec(
        "no-delete-action",
        "train",
        "refusal_handoff",
        "xóa dữ liệu",
        "xóa dữ liệu",
        (
            "mình muốn xóa luôn bản ghi này",
            "mình cần loại bỏ dữ liệu mà không lưu dấu vết",
            "mình muốn dọn toàn bộ lịch sử",
            "mình cần hủy dữ liệu thay cho chủ sở hữu",
            "mình muốn bỏ qua thời hạn lưu giữ",
        ),
        (
            "chuẩn bị yêu cầu xóa có phạm vi và lý do rõ ràng",
            "giữ nhật ký kiểm tra và chuyển người có thẩm quyền",
            "liệt kê dữ liệu dẫn xuất cần xử lý theo lineage",
            "xác minh chủ thể và chính sách trước khi đề xuất",
            "đối chiếu thời hạn lưu giữ rồi mới lập kế hoạch xóa",
        ),
    ),
    FamilySpec(
        "source-validity",
        "train",
        "citation_transparency",
        "hiệu lực của nguồn",
        "nguồn",
        (
            "mình đang kiểm tra một trích dẫn được lưu từ lâu",
            "mình cần dùng một nội dung đã lưu từ trước",
            "mình muốn xác nhận bản nào mới hơn",
            "mình cần trả lời dựa trên tài liệu đang có",
            "mình muốn biết có thể tin vào ghi chú này không",
        ),
        (
            "hãy đối chiếu nơi phát hành và mốc bắt đầu áp dụng",
            "hãy kiểm tra phiên bản trước khi dùng nội dung cũ",
            "cần quan hệ thay thế được người phụ trách xác nhận",
            "chỉ kết luận từ tài liệu đã được phát hành",
            "đối chiếu ghi chú với nguồn gốc và thời điểm tạo",
        ),
    ),
    FamilySpec(
        "current-condition",
        "train",
        "citation_transparency",
        "điều kiện hiện hành",
        "điều kiện",
        (
            "mình muốn biết điều kiện đang áp dụng",
            "mình cần giải thích một quy tắc hiện tại",
            "mình muốn trả lời câu hỏi có thể đã thay đổi",
            "mình cần biết ngoại lệ nào còn hiệu lực",
            "mình muốn xác nhận nội dung trước khi tư vấn",
        ),
        (
            "cần văn bản gốc và ngày áp dụng",
            "đối chiếu đúng mục trong nguồn đang hiệu lực",
            "xác nhận thời điểm câu hỏi trước khi trả lời",
            "cần nguồn nêu rõ ngoại lệ và phạm vi",
            "kiểm tra phiên bản rồi mới dùng làm căn cứ",
        ),
    ),
    FamilySpec(
        "current-cost",
        "train",
        "citation_transparency",
        "thông tin có thể thay đổi",
        "thông tin",
        (
            "mình muốn biết một con số hiện tại",
            "mình cần báo lại mức áp dụng gần nhất",
            "mình muốn dùng con số từng thấy trước đây",
            "mình cần so sánh hai mốc khác nhau",
            "mình muốn trả lời nhanh dù chưa có tài liệu",
        ),
        (
            "cần nguồn chính thức kèm thời điểm công bố",
            "hãy lấy đúng phiên bản cho thời điểm được hỏi",
            "không nên dùng lại con số cũ khi chưa kiểm tra",
            "cần hai nguồn có mốc hiệu lực tương ứng",
            "nên nói chưa xác minh thay vì đưa ra con số đoán",
        ),
    ),
    FamilySpec(
        "action-receipt",
        "train",
        "state_transparency",
        "biên nhận hành động",
        "biên nhận",
        (
            "mình muốn biết yêu cầu đã được gửi chưa",
            "mình cần xác nhận việc vừa làm đã thành công",
            "mình muốn coi trạng thái là hoàn tất",
            "mình cần bằng chứng để bàn giao",
            "mình muốn biết hệ thống đã nhận nội dung chưa",
        ),
        (
            "cần mã biên nhận trước khi xác nhận đã gửi",
            "hãy kiểm tra phản hồi thành công từ hệ thống",
            "chỉ đổi trạng thái khi có sự kiện hợp lệ",
            "lưu mã tương quan và thời điểm xử lý",
            "đối chiếu mã yêu cầu với phản hồi nhận được",
        ),
    ),
    FamilySpec(
        "clarify-owner",
        "validation",
        "clarification",
        "người phụ trách",
        "người phụ trách",
        (
            "mình muốn chuyển việc này nhưng chưa biết cho ai",
            "mình cần người xác nhận kết quả",
            "mình muốn hỏi đúng bộ phận",
            "mình cần biết ai có thể quyết định",
            "mình muốn tránh gửi vòng quanh",
        ),
        (
            "việc này thuộc nội dung, dữ liệu hay vận hành",
            "ai đang sở hữu quy trình liên quan",
            "bạn cần tư vấn hay quyết định có thẩm quyền",
            "quyết định này ảnh hưởng tới phạm vi nào",
            "bạn đã có đầu mối hoặc mã yêu cầu trước đó chưa",
        ),
    ),
    FamilySpec(
        "handoff-sensitive",
        "validation",
        "refusal_handoff",
        "nội dung nhạy cảm",
        "nội dung nhạy cảm",
        (
            "mình muốn đưa thông tin riêng vào bản nháp",
            "mình cần gửi dữ liệu nhạy cảm qua kênh bất kỳ",
            "mình muốn bỏ bước che thông tin",
            "mình cần chia sẻ toàn bộ nội dung để tiện xử lý",
            "mình muốn lưu tạm thông tin bí mật trong ghi chú",
        ),
        (
            "loại bỏ dữ liệu không cần thiết trước khi bàn giao",
            "chuyển qua kênh đã được kiểm soát",
            "che thông tin rồi mới tạo bản nháp",
            "chỉ chia sẻ phần tối thiểu cho mục đích xử lý",
            "dùng kho bí mật phù hợp thay vì ghi chú thông thường",
        ),
    ),
    FamilySpec(
        "citation-scope",
        "validation",
        "citation_transparency",
        "phạm vi trích dẫn",
        "trích dẫn",
        (
            "mình có một nguồn nhưng không chắc nó trả lời đúng câu hỏi",
            "mình muốn dùng một đoạn gần giống nội dung cần trả lời",
            "mình cần biết nguồn có đủ mạnh để kết luận không",
            "mình muốn ghép hai nguồn khác thời điểm",
            "mình cần trả lời khi nguồn chỉ nói một phần",
        ),
        (
            "đối chiếu từng khẳng định với đoạn nguồn liên quan",
            "không suy rộng quá nội dung được trích",
            "kiểm tra nguồn có nêu đúng phạm vi và đối tượng",
            "xác nhận hai nguồn cùng phiên bản hoặc giải thích khác biệt",
            "nêu rõ phần đã có bằng chứng và phần còn thiếu",
        ),
    ),
    FamilySpec(
        "state-update",
        "validation",
        "state_transparency",
        "cập nhật trạng thái",
        "trạng thái",
        (
            "mình muốn biết bản ghi đã được cập nhật chưa",
            "mình cần xác nhận thay đổi đã lưu",
            "mình muốn báo lại là công việc đã xong",
            "mình cần biết tiến trình đang ở bước nào",
            "mình muốn phân biệt đang xử lý với hoàn tất",
        ),
        (
            "cần biên nhận ghi nhận thay đổi thành công",
            "hãy kiểm tra phiên bản mới trước khi xác nhận",
            "chỉ báo hoàn tất khi mọi bước bắt buộc đã qua",
            "đối chiếu trạng thái với sự kiện gần nhất",
            "dùng trạng thái trung gian cho tới khi có kết quả cuối",
        ),
    ),
    FamilySpec(
        "test-concise",
        "test",
        "concise_structure",
        "nội dung bàn giao",
        "bàn giao",
        (
            "mình cần bàn giao một việc đang dở",
            "mình muốn người nhận hiểu nhanh tình huống",
            "mình cần ghi phần còn thiếu",
            "mình muốn chốt trách nhiệm tiếp theo",
            "mình cần một ghi chú không lan man",
        ),
        (
            "nêu bối cảnh, trạng thái và việc kế tiếp",
            "ghi mục tiêu rồi liệt kê tối đa ba ý",
            "đánh dấu rõ dữ kiện còn phải xác minh",
            "ghi người nhận, đầu việc và mốc theo dõi",
            "giữ quyết định và bỏ chi tiết không cần thiết",
        ),
    ),
    FamilySpec(
        "test-clarify",
        "test",
        "clarification",
        "phạm vi yêu cầu",
        "phạm vi",
        (
            "mình cần hỗ trợ nhưng chưa xác định phạm vi",
            "mình muốn giải quyết cả nhóm vấn đề",
            "mình chưa biết yêu cầu này áp dụng cho ai",
            "mình đang khoanh vùng các bước trong một quy trình dài",
            "mình muốn tránh câu trả lời quá chung",
        ),
        (
            "bạn đang hỏi cho một trường hợp hay nhiều trường hợp",
            "vấn đề nào gây ảnh hưởng lớn nhất lúc này",
            "đối tượng và bối cảnh sử dụng cụ thể là gì",
            "bước nào đang cản trở kết quả cần đạt",
            "kết quả cụ thể bạn muốn nhận là gì",
        ),
    ),
    FamilySpec(
        "test-refusal",
        "test",
        "refusal_handoff",
        "thay đổi có tác động",
        "thay đổi",
        (
            "mình muốn áp dụng thay đổi ngay",
            "mình cần bỏ qua người kiểm tra",
            "mình muốn dùng quyền của người khác",
            "mình cần thực hiện mà không lưu biên nhận",
            "mình muốn tự xác nhận rủi ro",
        ),
        (
            "chuẩn bị mô tả thay đổi và phương án khôi phục",
            "chuyển người kiểm tra độc lập trước khi thực hiện",
            "xin đúng quyền tối thiểu cho người thao tác",
            "bắt buộc giữ biên nhận và lịch sử xử lý",
            "chuyển rủi ro tới người có thẩm quyền quyết định",
        ),
    ),
    FamilySpec(
        "test-citation",
        "test",
        "citation_transparency",
        "kết luận có nguồn",
        "kết luận",
        (
            "mình muốn kết luận từ một ghi chú ngắn",
            "mình chỉ có bản chép không ghi thời điểm",
            "mình muốn trả lời dù nguồn đã cũ",
            "mình cần biết có thể suy ra thêm không",
            "mình muốn dùng nguồn không rõ chủ sở hữu",
        ),
        (
            "cần quay lại tài liệu gốc trước khi kết luận",
            "tìm ngày ban hành và thời điểm bắt đầu áp dụng",
            "hãy tìm nguồn thay thế đang còn hiệu lực",
            "chỉ nêu điều được nguồn hỗ trợ trực tiếp",
            "cần nguồn gốc và người phụ trách trước khi sử dụng",
        ),
    ),
    FamilySpec(
        "test-state",
        "test",
        "state_transparency",
        "xác nhận hoàn tất",
        "xác nhận",
        (
            "mình đang đối chiếu một tác vụ chạy nền",
            "mình cần báo kết quả ngay",
            "mình muốn coi phản hồi tạm là thành công",
            "mình cần xác nhận thao tác đã chạy",
            "mình muốn bỏ qua bước kiểm tra cuối",
        ),
        (
            "đợi sự kiện kết thúc có chữ ký trước khi cập nhật",
            "hãy nêu đang chờ thay vì báo thành công",
            "phản hồi tạm chưa đủ để đổi trạng thái",
            "đối chiếu mã thao tác và kết quả trả về",
            "giữ trạng thái chưa hoàn tất cho tới khi kiểm tra xong",
        ),
    ),
)


def build_v4_candidate(*, generator_source_sha256: str) -> GeneratedCandidate:
    labels = _behavior_labels()
    families: list[dict[str, Any]] = []
    scenario_requests: dict[str, tuple[str, str]] = {}
    for family in _FAMILIES:
        scenarios: list[dict[str, str]] = []
        for variant in range(25):
            scenario_id = f"{family.family_id}-{variant + 1:02d}"
            user, assistant = _render_messages(family, variant)
            seed_digest = digest(
                {
                    "family_id": family.family_id,
                    "seed_set_id": _SEED_SET_ID,
                    "variant": variant,
                }
            )
            scenario_digest = digest(
                {"assistant": assistant, "scenario_id": scenario_id, "user": user}
            )
            scenarios.append(
                {
                    "scenario_digest": scenario_digest,
                    "scenario_id": scenario_id,
                    "seed_digest": seed_digest,
                }
            )
            scenario_requests[scenario_id] = (user, assistant)
        families.append(
            {
                "behavior": family.behavior,
                "family_id": family.family_id,
                "scenarios": scenarios,
                "semantic_fingerprint": digest(
                    {
                        "behavior": family.behavior,
                        "subject": family.subject,
                    }
                ),
                "split": family.split,
            }
        )
    family_lock: dict[str, Any] = {
        "candidate_id": _CANDIDATE_ID,
        "families": families,
    }
    pinned: dict[str, Any] = {
        "behavior_labels": labels,
        "candidate_id": _CANDIDATE_ID,
        "domain_pack_sha256": ("23b16f3cf148f456c8ffd8c510fa7e44352e56baf7925b17b6b727b856414b57"),
        "exports": ["gemini/train.jsonl", "gemini/validation.jsonl"],
        "generator_identity": _GENERATOR_IDENTITY,
        "generator_revision": "synthetic-behavior-composer-v4",
        "generator_source_sha256": generator_source_sha256,
        "security_policy_sha256": (
            "5190c7d66acc8a8b80f9fe6fcda21b20c11fd33bb7383ca24d5789668790282d"
        ),
        "seed_set_id": _SEED_SET_ID,
        "source": "synthetic",
        "system_instruction": _SYSTEM_INSTRUCTION,
        "verifier_revision": "synthetic-tuning-candidate-v2",
        "voice_rubric_sha256": ("548051aab2d5f019693c0a45d94dfc421296300555de5ea1e424a4807c9e9f2d"),
        "work_item": _WORK_ITEM,
    }
    pinned_digest = digest(pinned)
    family_digest = digest(family_lock)
    records: list[dict[str, Any]] = []
    for family in _FAMILIES:
        locked = next(value for value in families if value["family_id"] == family.family_id)
        scenarios = cast(list[dict[str, str]], locked["scenarios"])
        for variant, scenario in enumerate(scenarios):
            user, assistant = scenario_requests[scenario["scenario_id"]]
            record_id = f"v4-{family.split}-{family.family_id}-{variant + 1:02d}"
            messages = [
                {"role": "user", "content": user},
                {"role": "assistant", "content": assistant},
            ]
            prompt_components = [f"prompt:{family.split}:{family.family_id}:{variant + 1:02d}"]
            response_components = [
                f"response-prefix:{family.split}:{family.family_id}:{variant + 1:02d}",
                f"response-bridge:{family.split}:{family.family_id}:{variant + 1:02d}",
                f"response-modifier:{family.split}:{family.family_id}:{variant + 1:02d}",
                f"response-tail:{family.split}:{family.family_id}:{variant + 1:02d}",
            ]
            lineage: dict[str, Any] = {
                "candidate_id": _CANDIDATE_ID,
                "composition_digest": digest(
                    {
                        "messages": messages,
                        "prompt_component_ids": prompt_components,
                        "response_component_ids": response_components,
                    }
                ),
                "family_lock_sha256": family_digest,
                "generation_run_id": _RUN_ID,
                "generator_identity": _GENERATOR_IDENTITY,
                "generator_source_sha256": generator_source_sha256,
                "golden_or_heldout_seed_refs": [],
                "pinned_revisions_sha256": pinned_digest,
                "prompt_component_ids": prompt_components,
                "record_content_sha256": "",
                "response_component_ids": response_components,
                "scenario_digest": scenario["scenario_digest"],
                "scenario_id": scenario["scenario_id"],
                "seed_digest": scenario["seed_digest"],
                "seed_set_id": _SEED_SET_ID,
                "source_refs": [],
                "work_item": _WORK_ITEM,
            }
            constraints = _constraints(family, variant, assistant)
            record: dict[str, Any] = {
                "family_id": family.family_id,
                "human_adjudicated": False,
                "labels": labels[family.behavior],
                "lineage": lineage,
                "messages": messages,
                "production_eligible": False,
                "provider_call_made": False,
                "record_id": record_id,
                "release_eligible": False,
                "response_constraints": constraints,
                "source": "synthetic",
                "split": family.split,
                "training_eligible": False,
                "upload_made": False,
            }
            projection = deepcopy(record)
            cast(dict[str, Any], projection["lineage"]).pop("record_content_sha256")
            lineage["record_content_sha256"] = digest(projection)
            records.append(record)
    return GeneratedCandidate(
        records=tuple(records),
        family_lock=family_lock,
        pinned_revisions=pinned,
        regression_manifest=_regression_manifest(records),
    )


def _behavior_labels() -> dict[str, dict[str, str]]:
    return {
        "concise_structure": {
            "behavior": "concise_structure",
            "language": "vi",
            "risk_category": "low",
            "training_intent": "response_economy",
        },
        "clarification": {
            "behavior": "clarification",
            "language": "vi",
            "risk_category": "medium",
            "training_intent": "ask_before_assuming",
        },
        "refusal_handoff": {
            "behavior": "refusal_handoff",
            "language": "vi",
            "risk_category": "high",
            "training_intent": "preserve_authority",
        },
        "citation_transparency": {
            "behavior": "citation_transparency",
            "language": "vi",
            "risk_category": "high",
            "training_intent": "refuse_unsupported_facts",
        },
        "state_transparency": {
            "behavior": "state_transparency",
            "language": "vi",
            "risk_category": "high",
            "training_intent": "never_fake_state",
        },
    }


def _render_messages(family: FamilySpec, variant: int) -> tuple[str, str]:
    opening = _OPENINGS[variant // 5]
    request = family.requests[variant % 5]
    focus = family.responses[variant % 5]
    lead = _RESPONSE_LEADS[family.behavior][variant // 5]
    user = f"{opening} {request}."
    if family.family_id == "clear-next-step" and variant < 4:
        assistant = (
            "Chốt mục tiêu, rồi ghi một bước tiếp theo thật cụ thể.",
            "Chọn việc cần xác nhận trước, rồi mới phân công.",
            "Tách điều đã biết khỏi điều còn phải hỏi.",
            "Xếp việc theo phụ thuộc và chốt mốc kiểm tra.",
        )[variant]
    elif family.behavior == "clarification":
        assistant = f"{lead} {focus}? Khi có thông tin này, mình sẽ hỗ trợ tiếp."
    elif family.behavior == "refusal_handoff":
        assistant = f"{lead} Mình có thể {focus}."
    elif family.behavior == "citation_transparency":
        assistant = f"{lead} {_sentence_case(focus)}."
    elif family.behavior == "state_transparency":
        assistant = f"{lead} {_sentence_case(focus)}."
    else:
        assistant = f"{lead} {focus}; như vậy yêu cầu sẽ rõ ràng hơn."
    return user, assistant


def _sentence_case(value: str) -> str:
    return value[:1].upper() + value[1:]


def _constraints(
    family: FamilySpec,
    variant: int,
    assistant: str,
) -> dict[str, Any]:
    max_words = 48
    required_phrases = [family.anchor] if family.anchor in assistant else []
    if family.family_id == "clear-next-step" and variant < 4:
        short = (
            "Chốt mục tiêu, rồi ghi một bước tiếp theo thật cụ thể.",
            "Chọn việc cần xác nhận trước, rồi mới phân công.",
            "Tách điều đã biết khỏi điều còn phải hỏi.",
            "Xếp việc theo phụ thuộc và chốt mốc kiểm tra.",
        )[variant]
        if assistant != short:
            max_words = 48
        else:
            max_words = 15
            required_phrases = []
    return {
        "forbidden_phrases": ["đã được phê duyệt", "đã hoàn tất thay bạn"],
        "max_questions": 1 if family.behavior == "clarification" else 0,
        "max_words": max_words,
        "required_phrases": required_phrases,
    }


def _regression_manifest(records: list[dict[str, Any]]) -> dict[str, Any]:
    replacements = [
        record
        for record in records
        if record["family_id"] == "clear-next-step" and record["split"] == "train"
    ][:4]
    return {
        "regressions": [
            {
                "replacement_record_id": replacement["record_id"],
                "replacement_record_sha256": replacement["lineage"]["record_content_sha256"],
                "replacement_word_count": count_words(str(replacement["messages"][1]["content"])),
                "requirement": "assistant-response-max-15-words",
                "source_record_id": source_id,
                "source_record_sha256": source_sha256,
                "source_word_count": source_word_count,
            }
            for (source_id, source_sha256, source_word_count), replacement in zip(
                _REGRESSION_SOURCES,
                replacements,
                strict=True,
            )
        ],
        "source_candidate": "vivi-behavior-synthetic-v2",
        "target_candidate": _CANDIDATE_ID,
    }
