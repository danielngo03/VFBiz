import { ApiProperty } from '@nestjs/swagger';
import {
  IsIn,
  IsInt,
  IsString,
  IsUUID,
  Max,
  MaxLength,
  Min,
  MinLength,
  ValidateNested,
} from 'class-validator';
import { Type } from 'class-transformer';

class ConversationTurnBudgetDto {
  @IsInt()
  @Min(1)
  @Max(32_000)
  maxModelTokens!: number;

  @IsInt()
  @Min(1)
  @Max(10_000_000)
  maxCostMicros!: number;
}

export class CreateConversationMessageDto {
  @IsIn(['message.enqueue'])
  kind!: 'message.enqueue';

  @ApiProperty({
    description: 'Client-generated UUID used for idempotent replay.',
    format: 'uuid',
  })
  @IsUUID('4')
  clientMessageId!: string;

  @ApiProperty({
    example: 'VF 8 có phạm vi hoạt động bao nhiêu?',
    maxLength: 4000,
    minLength: 1,
  })
  @IsString()
  @MinLength(1)
  @MaxLength(4000)
  content!: string;

  @ApiProperty({
    description:
      'Conversation version last observed by the client. A stale value is rejected.',
    example: 0,
    minimum: 0,
  })
  @IsInt()
  @Min(0)
  @Max(Number.MAX_SAFE_INTEGER)
  expectedVersion!: number;

  @ValidateNested()
  @Type(() => ConversationTurnBudgetDto)
  budget!: ConversationTurnBudgetDto;
}
