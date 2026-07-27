import { Module } from '@nestjs/common';
import { InternalAiTrustConfig } from '../config/internal-ai-trust.config';
import { InternalAiAssertionKeyring } from './internal-ai-assertion-keyring';
import { InternalAiAssertionSigner } from './internal-ai-assertion-signer';
import { InternalAiJwksExporter } from './internal-ai-jwks-exporter';
import { InternalAiJwksController } from './internal-ai-jwks.controller';

@Module({
  controllers: [InternalAiJwksController],
  providers: [
    InternalAiTrustConfig,
    InternalAiAssertionKeyring,
    InternalAiAssertionSigner,
    InternalAiJwksExporter,
  ],
  exports: [
    InternalAiTrustConfig,
    InternalAiAssertionSigner,
    InternalAiJwksExporter,
  ],
})
export class InternalAiTrustModule {}
