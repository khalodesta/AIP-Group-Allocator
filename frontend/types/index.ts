export type Participant={id:string;name:string;attributes:Record<string,string|number|null>};
export type Factor={id:string;name:string;source_column:string;data_type:string;strategy:string;weight:number;enabled:boolean;missing_handling:string};
export type Activity={id:string;name:string;mode:string;value:number;locked:boolean};
export type Configuration={schema_version:number;activities:Activity[];factors:Factor[];seed:number;time_limit_seconds:number;repeat_weight:number};
export type Group={id:string;name:string;participant_ids:string[]};
export type Allocation={activities:{activity_id:string;activity_name:string;groups:Group[];locked:boolean}[];status:string;objective_value?:number;seed:number};
export type Metrics={total_participants:number;total_unique_pairs:number;average_unique_teammates:number;minimum_unique_teammates:number;repeat_pairing_penalty:number;normalized_unique_pair_rate:number;pair_overlap:Record<string,number>;factor_balance_scores:Record<string,number>;participant_exposure:Record<string,number>;same_university_pairs:number;gender_balance_deviation:number;activity_group_details:Record<string,unknown[]>};
