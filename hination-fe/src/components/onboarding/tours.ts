import type { DriveStep } from "driver.js";

import type { TourPage } from "@/lib/onboarding";

// Per-page guided-tour step catalogs (data only). Steps anchor to `data-tour="..."` attributes
// added to the real controls on each screen. A step with no `element` renders as a centered
// welcome card. Steps whose target element is absent (e.g. the chief-only SMS controls for an
// anonymous viewer) are filtered out at runtime in OnboardingTour, so it is safe to list them.
// All copy is Vietnamese to match the app.

export const TOUR_STEPS: Record<TourPage, DriveStep[]> = {
  map: [
    {
      popover: {
        title: "Chào mừng đến Điện Biên Forecast 👋",
        description:
          "Bản đồ hiển thị mức cảnh báo thiên tai của từng xã trong 7 ngày tới. Cùng xem nhanh cách dùng nhé.",
      },
    },
    {
      element: '[data-tour="map-nav"]',
      popover: {
        title: "Chuyển màn hình",
        description:
          "Mở menu để đi tới Quản lý người dân, Đài phát thanh và Cứu hộ.",
        side: "right",
        align: "start",
      },
    },
    {
      element: '[data-tour="map-timeline"]',
      popover: {
        title: "Dự báo 7 ngày",
        description:
          "Chọn ngày và kéo thanh giờ để xem mức nguy hiểm thay đổi theo từng giờ.",
        side: "top",
        align: "center",
      },
    },
    {
      element: '[data-tour="map-legend"]',
      popover: {
        title: "Chú giải & bộ lọc",
        description:
          "Bật chú giải để lọc theo loại thiên tai, xem thang mức nguy hiểm và hiện các yêu cầu cứu hộ trên bản đồ.",
        side: "bottom",
        align: "end",
      },
    },
    {
      element: '[data-tour="map-bell"]',
      popover: {
        title: "Cảnh báo đang hoạt động",
        description:
          "Chuông hiện các khu vực đang nguy hiểm, sắp xếp theo thời điểm đỉnh gần nhất.",
        side: "bottom",
        align: "end",
      },
    },
    {
      element: '[data-tour="map-blast"]',
      popover: {
        title: "Gửi SMS cảnh báo",
        description:
          "Gửi nhanh tin nhắn SMS tới người dân ở các khu vực đang nguy hiểm.",
        side: "bottom",
        align: "end",
      },
    },
    {
      element: '[data-tour="map-refresh"]',
      popover: {
        title: "Làm mới dữ liệu",
        description: "Tải lại toàn bộ dự báo và cảnh báo mới nhất.",
        side: "bottom",
        align: "start",
      },
    },
    {
      element: '[data-tour="map-sos"]',
      popover: {
        title: "Trợ giúp khẩn cấp",
        description:
          "Người dân bấm vào đây để gửi yêu cầu cứu hộ kèm vị trí và gọi số khẩn cấp gần nhất.",
        side: "left",
        align: "end",
      },
    },
  ],

  manage: [
    {
      popover: {
        title: "Quản lý người dân 👋",
        description:
          "Đây là nơi quản lý danh bạ người dân để gửi cảnh báo. Xem nhanh các tính năng chính.",
      },
    },
    {
      element: '[data-tour="nav-sidebar"]',
      popover: {
        title: "Điều hướng",
        description: "Chuyển giữa Bản đồ, Quản lý, Đài phát thanh và Cứu hộ tại đây.",
        side: "right",
        align: "start",
      },
    },
    {
      element: '[data-tour="manage-add"]',
      popover: {
        title: "Thêm & nhập người dân",
        description: "Thêm từng người hoặc nhập danh sách để mở rộng danh bạ nhận cảnh báo.",
        side: "bottom",
        align: "end",
      },
    },
    {
      element: '[data-tour="manage-search"]',
      popover: {
        title: "Tìm & lọc",
        description: "Tìm theo tên và lọc người dân theo khu vực.",
        side: "bottom",
        align: "start",
      },
    },
    {
      element: '[data-tour="manage-table"]',
      popover: {
        title: "Danh sách người dân",
        description: "Xem, sửa hoặc xóa thông tin từng người dân trong bảng này.",
        side: "top",
        align: "center",
      },
    },
  ],

  radio: [
    {
      popover: {
        title: "Đài phát thanh 👋",
        description:
          "Soạn và phát cảnh báo bằng giọng nói tới loa phường. Xem nhanh cách dùng.",
      },
    },
    {
      element: '[data-tour="nav-sidebar"]',
      popover: {
        title: "Điều hướng",
        description: "Chuyển giữa Bản đồ, Quản lý, Đài phát thanh và Cứu hộ tại đây.",
        side: "right",
        align: "start",
      },
    },
    {
      element: '[data-tour="radio-compose"]',
      popover: {
        title: "Soạn nội dung cảnh báo",
        description:
          "Chọn khu vực, soạn nội dung và tạo bản tin cảnh báo để phát cho người dân.",
        side: "top",
        align: "center",
      },
    },
    {
      element: '[data-tour="radio-recordings"]',
      popover: {
        title: "Giọng nói đã lưu",
        description: "Nghe lại, đổi tên hoặc dùng lại các bản ghi âm đã lưu.",
        side: "top",
        align: "center",
      },
    },
    {
      element: '[data-tour="radio-history"]',
      popover: {
        title: "Bản nháp & lịch sử phát",
        description: "Theo dõi các bản nháp và những lần đã phát trước đây.",
        side: "top",
        align: "center",
      },
    },
  ],

  rescue: [
    {
      popover: {
        title: "Cứu hộ 👋",
        description:
          "Theo dõi yêu cầu cứu trợ khẩn cấp và quản lý số điện thoại cứu hộ. Xem nhanh cách dùng.",
      },
    },
    {
      element: '[data-tour="nav-sidebar"]',
      popover: {
        title: "Điều hướng",
        description: "Chuyển giữa Bản đồ, Quản lý, Đài phát thanh và Cứu hộ tại đây.",
        side: "right",
        align: "start",
      },
    },
    {
      element: '[data-tour="rescue-tabs"]',
      popover: {
        title: "Yêu cầu & số khẩn cấp",
        description:
          "Chuyển giữa danh sách yêu cầu cứu trợ và các số điện thoại khẩn cấp hiển thị cho người dân.",
        side: "bottom",
        align: "start",
      },
    },
    {
      element: '[data-tour="rescue-requests"]',
      popover: {
        title: "Danh sách cần trợ giúp",
        description:
          "Mỗi thẻ là một người dân đang cần cứu trợ, kèm vị trí gần nhất để điều phối.",
        side: "top",
        align: "center",
      },
    },
  ],
};
