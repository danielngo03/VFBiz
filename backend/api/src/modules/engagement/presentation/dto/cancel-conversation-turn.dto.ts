import { ApiProperty } from '@nestjs/swagger';
import { IsInt, Max, Min } from 'class-validator';

export class CancelConversationTurnDto {
  @ApiProperty({
    description:
      'Conversation version last observed by the client. Cancellation uses OCC and rejects stale versions.',
    minimum: 0,
  })
  @IsInt()
  @Min(0)
  @Max(Number.MAX_SAFE_INTEGER)
  expectedVersion!: number;
}
