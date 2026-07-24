INSERT INTO source_revision (id, source, revision, checksum, "effectiveAt")
VALUES ('00000000-0000-0000-0000-000000000001', 'fixture', 'r1', repeat('a', 64), now());

INSERT INTO vehicle_model (id, slug, name, category, "commercialStatus", "sourceRevisionId", "effectiveAt", "updatedAt")
VALUES ('00000000-0000-0000-0000-000000000010', 'vf-test', 'VF Test', 'suv', 'active', '00000000-0000-0000-0000-000000000001', now(), now());

INSERT INTO vehicle_variant (id, "vehicleModelId", code, name, specifications, "commercialStatus", "sourceRevisionId", "effectiveAt", "updatedAt")
VALUES ('00000000-0000-0000-0000-000000000011', '00000000-0000-0000-0000-000000000010', 'VF-TEST-1', 'VF Test 1', '{}', 'active', '00000000-0000-0000-0000-000000000001', now(), now());

INSERT INTO identity_subject (id, issuer, subject, realm, "updatedAt")
VALUES ('00000000-0000-0000-0000-000000000020', 'https://ciam.example', 'subject-1', 'customer', now());

INSERT INTO session_projection (id, "identitySubjectId", "sessionRefHash", "authenticatedAt", "expiresAt")
VALUES ('00000000-0000-0000-0000-000000000021', '00000000-0000-0000-0000-000000000020', repeat('b', 64), now(), now() + interval '1 hour');

INSERT INTO customer_profile (id, "identitySubjectId", "updatedAt")
VALUES ('00000000-0000-0000-0000-000000000030', '00000000-0000-0000-0000-000000000020', now());

INSERT INTO consent_event (id, "customerProfileId", purpose, "policyVersion", state, source)
VALUES ('00000000-0000-0000-0000-000000000031', '00000000-0000-0000-0000-000000000030', 'analytics', 'v1', 'granted', 'portal');

INSERT INTO customer_vehicle_reference (id, "customerProfileId", "vehicleVariantId", nickname, "updatedAt")
VALUES ('00000000-0000-0000-0000-000000000032', '00000000-0000-0000-0000-000000000030', '00000000-0000-0000-0000-000000000011', NULL, now());

INSERT INTO vehicle_energy_profile (id, "vehicleVariantId", "usableBatteryKwh", "baseConsumptionWhPerKm", "auxiliaryPowerKw", "reserveSocPercent", "connectorStandards", "chargingCurve", "sourceRevisionId", "validFrom")
VALUES ('00000000-0000-0000-0000-000000000040', '00000000-0000-0000-0000-000000000011', 80, 180, 1.2, 10, ARRAY['CCS2'], '{}', '00000000-0000-0000-0000-000000000001', now());

INSERT INTO charging_station (id, "externalRef", name, latitude, longitude, status, "sourceRevisionId", "refreshedAt")
VALUES ('00000000-0000-0000-0000-000000000050', 'station-1', 'Trạm thử nghiệm', 10.77, 106.69, 'available', '00000000-0000-0000-0000-000000000001', now());

INSERT INTO charging_connector (id, "chargingStationId", standard, "maximumPowerKw", status)
VALUES ('00000000-0000-0000-0000-000000000051', '00000000-0000-0000-0000-000000000050', 'CCS2', 150, 'available');

INSERT INTO charging_tariff (id, "chargingConnectorId", currency, "pricePerKwhMinor", "sourceRevisionId", "validFrom")
VALUES ('00000000-0000-0000-0000-000000000052', '00000000-0000-0000-0000-000000000051', 'VND', 3500, '00000000-0000-0000-0000-000000000001', now());

INSERT INTO trip_plan_projection (id, "customerProfileId", "vehicleEnergyProfileId", "requestFingerprint", result, "sourceRevisions", "expiresAt")
VALUES ('00000000-0000-0000-0000-000000000060', '00000000-0000-0000-0000-000000000030', '00000000-0000-0000-0000-000000000040', repeat('c', 64), '{}', '{}', now() + interval '1 hour');

INSERT INTO conversation_session (id, "customerProfileId", "assistantProfile", status, "policyRevision", "updatedAt")
VALUES ('00000000-0000-0000-0000-000000000070', '00000000-0000-0000-0000-000000000030', 'authenticated_customer', 'active', 'p1', now());

INSERT INTO conversation_message (id, "conversationSessionId", role, "redactedContent", citations)
VALUES ('00000000-0000-0000-0000-000000000071', '00000000-0000-0000-0000-000000000070', 'assistant', 'Nội dung đã lọc', '[]');
