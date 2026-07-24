import {
  BadRequestException,
  Controller,
  Get,
  NotFoundException,
  Param,
  Query,
  ServiceUnavailableException,
} from '@nestjs/common';
import {
  ApiBadRequestResponse,
  ApiNotFoundResponse,
  ApiOkResponse,
  ApiOperation,
  ApiParam,
  ApiQuery,
  ApiServiceUnavailableResponse,
  ApiTags,
} from '@nestjs/swagger';
import { Public } from '../../../platform/http/public.decorator';
import { ReadVehicleCatalogService } from '../application/services/read-vehicle-catalog.service';
import { ReadCommercialDataService } from '../application/services/read-commercial-data.service';
import { CommercialFactUnavailableError } from '../domain/commercial-facts';
import { VehicleCatalogUnavailableError } from '../domain/vehicle-catalog';
import {
  VehicleCommercialDto,
  VehicleModelCatalogDto,
} from './dto/vehicle-catalog.dto';

function checkedMarket(market: string | undefined): string {
  if (market === undefined || market.toUpperCase() === 'VN') return 'VN';
  throw new BadRequestException({
    code: 'UNSUPPORTED_MARKET',
    message: 'The requested vehicle market is not supported.',
  });
}

function mapCatalogError(error: unknown): never {
  if (error instanceof VehicleCatalogUnavailableError) {
    throw new ServiceUnavailableException({
      code: 'VEHICLE_CATALOG_UNAVAILABLE',
      message: 'A verified fresh vehicle catalog is temporarily unavailable.',
    });
  }
  throw error;
}

@Controller({ path: 'vehicles/models', version: '1' })
@Public()
@ApiTags('Vehicle Catalog')
export class VehicleCatalogController {
  constructor(
    private readonly catalog: ReadVehicleCatalogService,
    private readonly commercial: ReadCommercialDataService,
  ) {}

  @Get()
  @ApiOperation({
    operationId: 'listVehicleModels',
    summary: 'List vehicle models',
    description:
      'Lists public vehicle model projections from the active approved catalog release.',
  })
  @ApiQuery({
    name: 'market',
    required: false,
    schema: { default: 'VN', enum: ['VN'], type: 'string' },
  })
  @ApiOkResponse({ type: [VehicleModelCatalogDto] })
  @ApiBadRequestResponse({ description: 'Unsupported market.' })
  @ApiServiceUnavailableResponse({
    description: 'No approved fresh catalog release is available.',
  })
  async list(
    @Query('market') market?: string,
  ): Promise<readonly VehicleModelCatalogDto[]> {
    try {
      return await this.catalog.list(checkedMarket(market));
    } catch (error) {
      return mapCatalogError(error);
    }
  }

  @Get(':slug')
  @ApiOperation({
    operationId: 'getVehicleModelBySlug',
    summary: 'Get vehicle model',
    description:
      'Returns one public vehicle model projection by stable slug and market.',
  })
  @ApiParam({ example: 'vf-8', name: 'slug' })
  @ApiQuery({
    name: 'market',
    required: false,
    schema: { default: 'VN', enum: ['VN'], type: 'string' },
  })
  @ApiOkResponse({ type: VehicleModelCatalogDto })
  @ApiBadRequestResponse({ description: 'Unsupported market.' })
  @ApiNotFoundResponse({
    description:
      'No vehicle model with this slug exists in the active catalog.',
  })
  @ApiServiceUnavailableResponse({
    description: 'No approved fresh catalog release is available.',
  })
  async get(
    @Param('slug') slug: string,
    @Query('market') market?: string,
  ): Promise<VehicleModelCatalogDto> {
    try {
      const model = await this.catalog.getBySlug(
        checkedMarket(market),
        slug.toLowerCase(),
      );
      if (model === null) {
        throw new NotFoundException({
          code: 'VEHICLE_MODEL_NOT_FOUND',
          message: 'The vehicle model was not found in the active catalog.',
        });
      }
      return model;
    } catch (error) {
      return mapCatalogError(error);
    }
  }

  @Get(':slug/commercial')
  @ApiOperation({
    operationId: 'getVehicleModelCommercialData',
    summary: 'Get current commercial data',
    description:
      'Returns governed public price offers and promotions from one active commercial release. Inventory is intentionally excluded.',
  })
  @ApiParam({ example: 'vf-8', name: 'slug' })
  @ApiQuery({
    name: 'market',
    required: false,
    schema: { default: 'VN', enum: ['VN'], type: 'string' },
  })
  @ApiOkResponse({ type: VehicleCommercialDto })
  @ApiBadRequestResponse({ description: 'Unsupported market.' })
  @ApiNotFoundResponse({
    description:
      'No vehicle model with this slug exists in the active catalog.',
  })
  @ApiServiceUnavailableResponse({
    description:
      'No approved, fresh and anomaly-free commercial release is available.',
  })
  async getCommercial(
    @Param('slug') slug: string,
    @Query('market') market?: string,
  ): Promise<VehicleCommercialDto> {
    const checked = checkedMarket(market);
    let model: VehicleModelCatalogDto | null;
    try {
      model = await this.catalog.getBySlug(checked, slug.toLowerCase());
    } catch (error) {
      return mapCatalogError(error);
    }
    if (model === null) {
      throw new NotFoundException({
        code: 'VEHICLE_MODEL_NOT_FOUND',
        message: 'The vehicle model was not found in the active catalog.',
      });
    }
    try {
      return await this.commercial.getForModel(model.id, checked);
    } catch (error) {
      if (error instanceof CommercialFactUnavailableError) {
        throw new ServiceUnavailableException({
          code: 'VEHICLE_COMMERCIAL_DATA_UNAVAILABLE',
          message:
            'Verified, fresh and anomaly-free commercial data is temporarily unavailable.',
        });
      }
      throw error;
    }
  }
}
