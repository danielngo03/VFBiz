import { randomUUID } from 'node:crypto';
import { Injectable } from '@nestjs/common';
import {
  ConversationRuntimeClock,
  ConversationRuntimeIdGenerator,
} from '../../application/runtime/conversation-runtime.repository';

@Injectable()
export class SystemConversationRuntimeClock extends ConversationRuntimeClock {
  now(): Date {
    return new Date();
  }
}

@Injectable()
export class UuidConversationRuntimeIdGenerator extends ConversationRuntimeIdGenerator {
  nextId(): string {
    return randomUUID();
  }
}
