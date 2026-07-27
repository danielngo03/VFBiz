import { ServiceUnavailableException } from '@nestjs/common';
import type { InternalAiTrustConfig } from '../config/internal-ai-trust.config';
import type { InternalAiJwksExporter } from './internal-ai-jwks-exporter';
import { InternalAiJwksController } from './internal-ai-jwks.controller';

describe('InternalAiJwksController', () => {
  it('exports public keys only while internal AI trust is enabled', () => {
    const keys = [{ alg: 'ES256', kid: 'key-1', kty: 'EC', use: 'sig' }];
    const controller = new InternalAiJwksController(
      { enabled: true } as InternalAiTrustConfig,
      { export: () => ({ keys }) } as unknown as InternalAiJwksExporter,
    );

    expect(controller.readPublicKeys()).toEqual({ keys });
    expect(controller.readPublicKeys().keys[0]).not.toHaveProperty('d');
  });

  it('fails closed while trust is disabled', () => {
    const controller = new InternalAiJwksController(
      { enabled: false } as InternalAiTrustConfig,
      {
        export: jest.fn(),
      } as unknown as InternalAiJwksExporter,
    );

    expect(() => controller.readPublicKeys()).toThrow(
      ServiceUnavailableException,
    );
  });
});
