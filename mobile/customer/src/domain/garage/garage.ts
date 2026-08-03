export type OwnershipVerification = "unverified" | "verified";

export interface GarageIdentity {
  entryId: string;
  isPrimary: boolean;
  verification: OwnershipVerification;
}
