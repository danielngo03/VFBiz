import { Injectable } from '@nestjs/common';
import { InternalAiAssertionKeyring } from './internal-ai-assertion-keyring';

@Injectable()
export class InternalAiJwksExporter {
  constructor(private readonly keyring: InternalAiAssertionKeyring) {}

  export(): ReturnType<InternalAiAssertionKeyring['publicJwks']> {
    return this.keyring.publicJwks();
  }
}
