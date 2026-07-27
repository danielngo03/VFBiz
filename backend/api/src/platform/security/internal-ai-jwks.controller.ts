import {
  Controller,
  Get,
  Header,
  ServiceUnavailableException,
} from '@nestjs/common';
import { ApiExcludeController } from '@nestjs/swagger';
import { InternalAiTrustConfig } from '../config/internal-ai-trust.config';
import { Public } from '../http/public.decorator';
import { InternalAiJwksExporter } from './internal-ai-jwks-exporter';

@ApiExcludeController()
@Controller({ path: 'internal/ai', version: '1' })
@Public()
export class InternalAiJwksController {
  constructor(
    private readonly config: InternalAiTrustConfig,
    private readonly exporter: InternalAiJwksExporter,
  ) {}

  @Get('jwks')
  @Header('Cache-Control', 'public, max-age=30, must-revalidate')
  readPublicKeys() {
    if (!this.config.enabled) {
      throw new ServiceUnavailableException({
        code: 'INTERNAL_AI_TRUST_DISABLED',
        message: 'Internal AI trust is not enabled.',
      });
    }
    return this.exporter.export();
  }
}
