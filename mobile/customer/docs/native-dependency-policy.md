# Chính sách native dependency của Customer

Chỉ thêm package khi Customer có capability và consumer thật. Hồ sơ admission:

- provenance, license, maintainer và release cadence;
- tương thích Expo 57, React Native 0.86, New Architecture và CNG;
- permission, privacy manifest, network/background behavior;
- config-plugin/prebuild diff iOS/Android;
- binary size, startup/performance và data collection;
- kill switch, rollback và phương án thay thế.

Ưu tiên Expo SDK module, sau đó package có config plugin duy trì tốt, rồi Expo
Module do Customer team sở hữu. Patch trực tiếp native project không được dùng
dưới CNG. Remote code, unreviewed binary, analytics mặc định hoặc secret trong
app config bị từ chối.

Upgrade chạy development build cả iOS/Android và kiểm auth callback, deep link,
cold start, offline transition, permissions. Không dùng `npm audit fix --force`;
exception cần advisory, reachability, mitigation, human owner, expiry và removal
work item.
