import { IsIn } from 'class-validator';
import { ApiProperty } from '@nestjs/swagger';

export class CreateConversationSessionDto {
  @ApiProperty({ enum: ['vi', 'en'], example: 'vi' })
  @IsIn(['vi', 'en'])
  locale!: 'vi' | 'en';

  @ApiProperty({
    enum: ['public_customer', 'authenticated_customer'],
    example: 'public_customer',
  })
  @IsIn(['public_customer', 'authenticated_customer'])
  profile!: 'public_customer' | 'authenticated_customer';
}
