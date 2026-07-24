import { ApiProperty } from '@nestjs/swagger';
import { IsString, MaxLength, MinLength } from 'class-validator';

export class CreateConversationMessageDto {
  @ApiProperty({
    example: 'VF 8 có phạm vi hoạt động bao nhiêu?',
    maxLength: 4000,
    minLength: 1,
  })
  @IsString()
  @MinLength(1)
  @MaxLength(4000)
  content!: string;
}
