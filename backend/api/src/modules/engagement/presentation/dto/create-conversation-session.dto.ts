import { IsIn } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class CreateConversationSessionDto {
  @ApiProperty({ enum: ['vi', 'en'], example: 'vi' })
  @IsIn(['vi', 'en'])
  locale!: 'vi' | 'en';
}
