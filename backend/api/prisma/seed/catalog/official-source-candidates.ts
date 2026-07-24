import {
  assertProductSourceCandidate,
  type ProductSourceCandidate,
} from '../../../src/modules/product/domain/product-source-candidate';

/**
 * Registry metadata only. These records intentionally have no checksum or
 * approval evidence, so no seed/import command may download or activate them.
 */
export const officialProductSourceCandidates = [
  {
    aiTrainingAllowed: false,
    approvalEvidenceRef: null,
    approvedByRef: null,
    documentCode: '20260711_ThongbaoCSgiabanvatrangbituychonotoVinFastVN',
    documentIssuedAt: '2026-07-11T00:00:00+07:00',
    expectedSha256: null,
    factValidityMode: 'single-window',
    id: 'product-source:vinfast-vn-vehicle-price-2026-07-11',
    market: 'VN',
    permittedPurposes: [],
    publisher: 'Công ty TNHH Kinh doanh Thương mại và Dịch vụ VinFast',
    rightsState: 'pending',
    sourceKind: 'official-public-document',
    sourceUrl:
      'https://static-cms-prod.vinfastauto.com/202607013_thong-bao-chinh-sach-gia-ban-cac-dong-xe-vinfast-thang-07.2026.pdf',
    submittedByRef: 'vfbiz-product-data-bootstrap',
    title:
      'Chính sách giá bán và trang bị tùy chọn ô tô điện VinFast tháng 07/2026',
  },
  {
    aiTrainingAllowed: false,
    approvalEvidenceRef: null,
    approvedByRef: null,
    documentCode: '202600718_ThongbaoCSthucdaybanhangotodienVinFasttaiVN',
    documentIssuedAt: '2026-07-18T00:00:00+07:00',
    expectedSha256: null,
    factValidityMode: 'per-fact',
    id: 'product-source:vinfast-vn-sales-policy-2026-07-18',
    market: 'VN',
    permittedPurposes: [],
    publisher: 'Công ty TNHH Kinh doanh Thương mại và Dịch vụ VinFast',
    rightsState: 'pending',
    sourceKind: 'official-public-document',
    sourceUrl:
      'https://static-cms-prod.vinfastauto.com/20260718_thong-bao-chinh-sach-thuc-day-ban-hang-o-to-dien-thang-07.2026_0.pdf',
    submittedByRef: 'vfbiz-product-data-bootstrap',
    title: 'Chính sách thúc đẩy bán hàng ô tô điện VinFast tháng 07/2026',
  },
] as const satisfies readonly ProductSourceCandidate[];

export function validateOfficialProductSourceCandidates(): void {
  const ids = new Set<string>();
  for (const candidate of officialProductSourceCandidates) {
    assertProductSourceCandidate(candidate);
    if (ids.has(candidate.id)) {
      throw new Error(`Duplicate product source candidate: ${candidate.id}`);
    }
    ids.add(candidate.id);
  }
}
