import { ApiProperty } from '@nestjs/swagger';
import { IsIn, IsInt, Max, Min } from 'class-validator';

export class RequestConversationHandoffDto {
  @IsIn(['handoff.request'])
  kind!: 'handoff.request';

  @ApiProperty({
    description:
      'Conversation version last observed by the client. Requesting handoff uses OCC and rejects stale versions.',
    minimum: 0,
  })
  @IsInt()
  @Min(0)
  @Max(Number.MAX_SAFE_INTEGER)
  expectedVersion!: number;

  @IsIn(['customer_requested'])
  reason!: 'customer_requested';
}
