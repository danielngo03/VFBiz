import { router } from "expo-router";
import { useMemo, useState } from "react";
import { Button, ListRow, LoadingState, ProblemState, Screen, Surface, Text, TextField, ToggleRow } from "../../../design/components";
import { useCreateGarageEntry } from "../../../state/mutations/garage-mutations";
import { useVehicleModels } from "../../../state/queries/customer-queries";

export default function AddGarageEntryRoute() {
  const models = useVehicleModels();
  const createEntry = useCreateGarageEntry();
  const [selectedVariantId, setSelectedVariantId] = useState<string | null>(null);
  const [nickname, setNickname] = useState("");
  const [search, setSearch] = useState("");
  const [isPrimary, setIsPrimary] = useState(false);
  const variants = useMemo(
    () =>
      (models.data?.data ?? []).flatMap((model) =>
        model.variants.map((variant) => ({
          modelName: model.name,
          modelYear: model.modelYear,
          variant,
        })),
      ),
    [models.data?.data],
  );
  const visibleVariants = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("vi");
    if (!query) return variants;
    return variants.filter(({ modelName, modelYear, variant }) =>
      `${modelName} ${variant.name} ${modelYear ?? ""}`
        .toLocaleLowerCase("vi")
        .includes(query),
    );
  }, [search, variants]);
  if (models.isLoading)
    return <Screen><LoadingState label="Đang tải danh mục xe" /></Screen>;
  if (models.isError)
    return <Screen><ProblemState title="Chưa tải được danh mục xe" detail="Không thể thêm xe khi chưa có catalog authority." /></Screen>;
  return (
    <Screen>
      <Text variant="display">Thêm xe</Text>
      <Text muted>Chọn đúng phiên bản từ danh mục được API phát hành. Garage entry vẫn là self-reported và chưa xác minh sở hữu.</Text>
      <TextField label="Tìm model hoặc phiên bản" value={search} onChangeText={setSearch} placeholder="Ví dụ: VF 8" />
      {variants.length === 0 ? (
        <ProblemState title="Danh mục đang trống" detail="App không cho nhập một model hoặc VIN không có trong contract." />
      ) : (
        <Surface>
          {visibleVariants.map(({ modelName, modelYear, variant }) => (
            <ListRow
              key={variant.id}
              icon="directions_car"
              title={`${modelName} · ${variant.name}`}
              detail={`${modelYear ?? "Năm chưa công bố"}`}
              trailing={selectedVariantId === variant.id ? "✓" : ""}
              onPress={() => setSelectedVariantId(variant.id)}
            />
          ))}
          {visibleVariants.length === 0 ? (
            <Text muted style={{ paddingVertical: 20, textAlign: "center" }}>Không có phiên bản phù hợp từ catalog.</Text>
          ) : null}
        </Surface>
      )}
      <TextField label="Tên gợi nhớ (không bắt buộc)" value={nickname} onChangeText={setNickname} placeholder="Ví dụ: Xe gia đình" />
      <Surface>
      <ToggleRow
        title="Đặt làm xe chính"
        detail="Dùng cho nội dung ưu tiên trên Trang chủ"
        value={isPrimary}
        onValueChange={setIsPrimary}
      />
      </Surface>
      {createEntry.isError ? (
        <ProblemState title="Chưa thêm được xe" detail={createEntry.error.message} />
      ) : null}
      <Button
        label={createEntry.isPending ? "Đang thêm…" : "Thêm vào Garage"}
        disabled={!selectedVariantId || createEntry.isPending}
        onPress={() => {
          if (!selectedVariantId) return;
          createEntry.mutate(
            {
              claimedVehicleVariantId: selectedVariantId,
              nickname: nickname.trim() || null,
              isPrimary,
            },
            { onSuccess: () => router.back() },
          );
        }}
      />
    </Screen>
  );
}
