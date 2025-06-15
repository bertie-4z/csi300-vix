import xframe.zh_public_api as xjlh

class CVIX:

    def __init__(self, 
                 stock_index, ## 沪深300 IO 还是 中证1000 MO
                 time_i, ## 分钟
                 gbsy, ## 当前分钟的国债即期收益率 ## Government Bond Spot Yield                 
                 ):
        
        self.time_i = time_i
        self.gbsy = gbsy
        ##self.contracts_df
        ##self.contracts_df_enddates
        ##self.oc_monthids_df
        ##self.tte_df
        ##self.Katm_df
        ##self.K0_df
        ##self.DKi_dict_df
        ##self.PQKi_df
        ##self.PQKi_amended_df
        ##self.Kcontribution_df
        ##self.final_df
        ##self.vix_value

        if not isinstance(stock_index, str):
            raise TypeError(f"input 'stock_index' must be a string, got {type(stock_index).__name__}")
        stock_index = stock_index.lower()  # Normalize
        if stock_index in ['csi300','沪深300', '300', 'hs300', 'hushen300', 'io', 'if', '000300.sh', '000300']:
            self.stock_index = 'IO'
        elif stock_index in ['csi1000','中证1000', '1000', 'zz1000', 'zhongzheng1000', 'mo', 'im' '000852.sh', '000852']:
            self.stock_index = 'MO'
        else:
            raise ValueError(f"Invalid stock_index value: {stock_index}")

        if not isinstance(time_i, dt.datetime):
            raise TypeError("Input 'time_i' must be  a datetime.datetime object")
        if time_i.time() == dt.time(0, 0):
            print("⚠️ Note: Time is set to midnight. Ensure this is intentional.")
        if not ((dt.time(9,30) <= time_i.time() <= dt.time(11,30)) or (dt.time(13,0) <= time_i.time() <= dt.time(15,0))):
            raise ValueError(f"Time {time_i.time()} is outside trading hours (09:30–11:30, 13:00–15:00)")
        
    
    def get_contracts_df(self):
        gaso = xjlh.get_all_securities(['options'],date=self.time_i.date().strftime('%Y%m%d'))
        contracts_df = gaso[gaso['ProductID']==self.stock_index]
        contracts_df = contracts_df.drop(['suspend', 'ExchangeID', 'name', 'ts_code', 'multiplier'], axis=1)
        contracts_df = contracts_df.set_index('code', drop=True)
        contracts_df.index.name = None
        contracts_df['start_date'] = pd.to_datetime(contracts_df['start_date']) + pd.Timedelta(hours=9, minutes=30)
        contracts_df['end_date'] = pd.to_datetime(contracts_df['end_date']) + pd.Timedelta(hours=15)
        contracts_df['MonthID'] = contracts_df.index.str[:6]
        contracts_df = contracts_df.sort_values(by='MonthID', ascending=True)
        contracts_df['MonthID first seen date'] = contracts_df.groupby('MonthID')['start_date'].transform('min')
        contracts_df['Strike'] = contracts_df.index.str[9:13].astype(int)
        
        self.contracts_df_enddates = contracts_df.groupby('MonthID').agg({'end_date': 'first'}).reset_index()
        self.contracts_df = contracts_df
        
        return self.contracts_df, self.contracts_df_enddates

    def get_oc_monthids_df(self): ## oc = Open Contracts ## NEEDS CHANGING (INDEX VALUE IS DT.DATE BUT NEEDS TO BE DATETIME)
        datedict = {'date': self.time_i}
        extantmonths = self.contracts_df['MonthID'][(self.contracts_df["MonthID first seen date"]<=self.time_i)&(self.contracts_df["end_date"]>=self.time_i)]
        extantmonths = list(dict.fromkeys(extantmonths))
        ## 近月、次近月、远月、近季、次近季、远季
        labels = ["m1合约", "m2合约", "m3合约", "q1合约", "q2合约", "q3合约"]
        for i, label in enumerate(labels):
            datedict[label] = extantmonths[i] if i < len(extantmonths) else np.nan
            
        oc_monthids_df = pd.DataFrame([datedict]).set_index('date', drop=True)
        oc_monthids_df.index.name = None
        self.oc_monthids_df = oc_monthids_df
        return self.oc_monthids_df

    def get_tte_df(self): ## tte = Time to Expiration (aka, 'NT')
        # tte_df = self.oc_monthids_df.copy()

        tte_df = self.contracts_df_enddates.copy()
        tte_df.index = pd.MultiIndex.from_product(
            [[self.oc_monthids_df.index[0]], self.oc_monthids_df.columns],
            names=['datetime_i', 'contract_label']
        )
        tte_df['tte_mins'] = tte_df['tte_mins'] = (tte_df['end_date'] - tte_df.index.get_level_values('datetime_i')).dt.total_seconds() / 60
        tte_df['tte_yr'] = tte_df['tte_mins'] / (365 * 24 * 60)
        
        self.tte_df = tte_df
        return self.tte_df
        
    def get_Katm_Fwd_df(self):
        Katm_Fwd_df = self.tte_df.copy()
        Katm_S_list = []
        Katm_diff_list = []
        for i1 in self.tte_df.index.get_level_values(1):
            monthid = self.tte_df.loc[self.time_i].loc[i1]['MonthID']
            tmc = self.contracts_df[self.contracts_df['MonthID']==monthid].copy() ## tmc = This Month's Contracts
            tmc['option_type'] = tmc.index.str[7:8]  # 'C' or 'P'
            tmc = tmc.reset_index().rename(columns={'index': 'code'})
            tmc_pivoted = tmc.pivot(index='Strike', columns='option_type', values='code')
            tmc_pivoted = tmc_pivoted.rename(columns={'C': 'C_codes', 'P': 'P_codes'})
            tmc_pivoted = tmc_pivoted.dropna()

            pdf = xjlh.get_price(security = tmc['code'].tolist(),
                                   start_date = self.time_i.strftime('%Y%m%d %H:%M'),
                                   end_date = self.time_i.strftime('%Y%m%d %H:%M'),
                                   frequency = '1m_his',
                                   fq = 'none',
                                   src='only_xjlh'
                                  ).pivot(index='code',columns='date',values='close')
            tmc_pivoted['C_prices'] = tmc_pivoted['C_codes'].map(pdf.iloc[:, 0])
            tmc_pivoted['P_prices'] = tmc_pivoted['P_codes'].map(pdf.iloc[:, 0])
            tmc_pivoted = tmc_pivoted.dropna()
            tmc_pivoted['CP_price_diff']= ( tmc_pivoted['C_prices'] - tmc_pivoted['P_prices'] ).abs()
            min_K = tmc_pivoted['CP_price_diff'].idxmin()
            min_K_diff = tmc_pivoted.loc[min_K]['CP_price_diff']
            Katm_S_list.append(min_K.astype(int))
            Katm_diff_list.append(min_K_diff)
        Katm_Fwd_df['S'] = Katm_S_list
        Katm_Fwd_df['CP_price_diff'] = Katm_diff_list
        Katm_Fwd_df['e^RT'] = np.exp( self.gbsy * Katm_Fwd_df['tte_yr'] ) 
        Katm_Fwd_df['F'] = Katm_Fwd_df['S'] + Katm_Fwd_df['e^RT'] * Katm_Fwd_df['CP_price_diff']
        
        self.Katm_Fwd_df = Katm_Fwd_df

        return self.Katm_Fwd_df

    def get_K0_df(self):
        K0_df = self.Katm_Fwd_df.copy()
        K0_df_list = []
        for i1 in self.tte_df.index.get_level_values(1):
            monthid = self.tte_df.loc[self.time_i].loc[i1]['MonthID']
            tmc = self.contracts_df[self.contracts_df['MonthID']==monthid].copy() ## tmc = This Month's Contracts
            tmc['option_type'] = tmc.index.str[7:8]  # 'C' or 'P'
            tmc = tmc.reset_index().rename(columns={'index': 'code'})
            tmc_pivoted = tmc.pivot(index='Strike', columns='option_type', values='code')
            tmc_pivoted = tmc_pivoted.rename(columns={'C': 'C_codes', 'P': 'P_codes'})
            tmc_pivoted = tmc_pivoted.dropna()

            K0 = tmc_pivoted.index[tmc_pivoted.index <= K0_df.loc[self.time_i].loc[i1]['F']].max()
            K0_df_list.append(K0)

        K0_df['K0'] = K0_df_list       
        self.K0_df = K0_df

        return self.K0_df

    def get_DKi_dict_df(self):
        Ki_dict = {}
        for i1 in self.tte_df.index.get_level_values(1):
            monthid = self.tte_df.loc[self.time_i].loc[i1]['MonthID']
            tmc = self.contracts_df[self.contracts_df['MonthID']==monthid].copy() ## tmc = This Month's Contracts
            tmc['option_type'] = tmc.index.str[7:8]  # 'C' or 'P'
            tmc = tmc.reset_index().rename(columns={'index': 'code'})
            tmc_p = tmc[tmc['option_type'] == 'P'].copy() 
            tmc_c = tmc[tmc['option_type'] == 'C'].copy()
            ## 'otm' = Out of The Money, 价外状态、虚值状态
            tmc_p_otm = tmc_p[tmc_p['Strike']<= self.K0_df.loc[self.time_i].loc[i1]['K0']].sort_values(by='Strike', ascending=True)
            tmc_c_otm = tmc_c[tmc_c['Strike']>= self.K0_df.loc[self.time_i].loc[i1]['K0']].sort_values(by='Strike', ascending=True)

            tm_Ki_df = pd.concat([tmc_p_otm,tmc_c_otm],axis=0)
            tm_Ki_df = tm_Ki_df.reset_index()

            Ki_dict[i1] = tm_Ki_df[['code','Strike']]

        Ki_dict_df = pd.concat(Ki_dict, axis=1).T
        new_index = pd.MultiIndex.from_tuples(
            [(self.time_i, contract_label, attribute)
            for contract_label, attribute in Ki_dict_df.index],
            names=['datetime_i', 'contract_label', Ki_dict_df.index.names[1]]
        )

        Ki_dict_df.index = new_index
        ## add ∆K
        DKi_dict = {}
        for idx, row in Ki_dict_df.loc[pd.IndexSlice[:,:, 'Strike'], :].iterrows():
            valid_Ks = row.dropna()
            K_diffs = []
            for col in valid_Ks.index: ## col is an integer value for each column number, starting from 0
                # val = valid_Ks[col]
                # Check left neighbor, right neighbor
                if col-1 in valid_Ks.index and col+1 in valid_Ks.index:
                    # middle K0 case
                    if valid_Ks[col] != valid_Ks[col+1] and valid_Ks[col] != valid_Ks[col-1]:
                        K_diffs.append((valid_Ks[col+1] - valid_Ks[col-1])/2)
                    if valid_Ks[col] != valid_Ks[col-1] and valid_Ks[col] == valid_Ks[col+1] and col+2 in valid_Ks.index:
                        K_diffs.append((valid_Ks[col+2] - valid_Ks[col-1])/2)
                    if valid_Ks[col] == valid_Ks[col-1] and valid_Ks[col] != valid_Ks[col+1] and col-2 in valid_Ks.index:
                        K_diffs.append((valid_Ks[col+1] - valid_Ks[col-2])/2)
                ## edge cases
                elif col-1 not in valid_Ks.index and col+1 in valid_Ks.index:
                    K_diffs.append(valid_Ks[col+1] - valid_Ks[col])
                elif col-1 in valid_Ks.index and col+1 not in valid_Ks.index:
                    K_diffs.append(valid_Ks[col] - valid_Ks[col-1])

            DKi_dict[(idx[0],idx[1],'DeltaK')] = pd.Series(K_diffs)

        DKi_dict_df = pd.concat(
            [ Ki_dict_df, pd.concat(DKi_dict, axis=1).T ],
            axis=0
        ).sort_index() 
    
        self.DKi_dict_df = DKi_dict_df
        return self.DKi_dict_df

    def get_PQKi_df(self):
        PQKi_dict = {}
        for idx, row in self.DKi_dict_df.loc[pd.IndexSlice[:,:, 'code'], :].iterrows():
            pdf = xjlh.get_price(
                security=row.dropna().tolist(),
                start_date=idx[0].strftime('%Y%m%d %H:%M'),
                end_date=idx[0].strftime('%Y%m%d %H:%M'),
                frequency='1d',
                fq='none',
                src='only_xjlh'
            ).pivot(index='code', columns='date', values='close')
            
            pdf = pdf.loc[row.dropna().tolist()]
            
            PQKi_dict[(idx[0],idx[1],'PQ(Ki)')] = pd.Series(pdf.values.flatten())

        PQKi_df = pd.concat(
                [self.DKi_dict_df, pd.concat(PQKi_dict, axis=1).T],
                axis=0
            ).sort_index()

        self.PQKi_df = PQKi_df

        PQKi_amended_df = self.PQKi_df.copy()
        for contract_level, group in PQKi_amended_df.groupby(level=1):
            grouped = group.T.groupby(group.loc[(self.time_i, contract_level, 'Strike')])
            for strike, g in grouped:
                if len(g)>1:
                    print(g)
                    first_col = g.index[0]
                    second_col = g.index[1]
                    PQKi_amended_df.at[(self.time_i, contract_level, 'PQ(Ki)'), first_col] = ( PQKi_amended_df.loc[(self.time_i, contract_level, 'PQ(Ki)'), first_col] \
                                                                                        +PQKi_amended_df.loc[(self.time_i, contract_level, 'PQ(Ki)'), second_col] ) /2
                    PQKi_amended_df.at[(self.time_i, contract_level, 'PQ(Ki)'), second_col] = 0
                    PQKi_amended_df.at[(self.time_i, contract_level, 'DeltaK'), second_col] = 0

        self.PQKi_amended_df = PQKi_amended_df

        return self.PQKi_df, self.PQKi_amended_df
    
    def get_Kcontribution_df(self): ## summation of the summands Σ
        Kcontribution_df = pd.DataFrame(index=self.tte_df.index)
        Kcontribution_df_list = []
        for contract_level, Kgroup in self.PQKi_amended_df.groupby(level=1):
            try:
                DeltaK_row = Kgroup.loc[pd.IndexSlice[:, [contract_level], ['DeltaK']]].values
                QKi_row = Kgroup.loc[pd.IndexSlice[:, [contract_level], ['PQ(Ki)']]].values
                K_row = Kgroup.loc[pd.IndexSlice[:, [contract_level], ['Strike']]].values
                eRT_row = self.Katm_Fwd_df.loc[(self.time_i,contract_level), 'e^RT']

                product_row = (DeltaK_row / K_row**2) * eRT_row * QKi_row # elementwise multiplication
                summed_product = np.nansum(product_row)  # sum over all strikes
                
                Kcontribution_df_list.append(summed_product)
            
            except KeyError:
                print(f"⚠️ Missing DeltaK or PQ(Ki) for {contract_level}")

        Kcontribution_df['Kcontribution'] = Kcontribution_df_list

        self.Kcontribution_df = Kcontribution_df
        return self.Kcontribution_df
    
    def get_final_df(self):
        final_df = pd.concat([self.K0_df, self.Kcontribution_df],axis=1)
        final_df['σ^2'] = (2/final_df['tte_yr']) * final_df['Kcontribution'] - (1/final_df['tte_yr'])*((final_df['F']/final_df['K0'] - 1)**2)
        self.final_df = final_df
        return self.final_df

    def get_vix(self, months_used = ['m1合约','m2合约']):
        NT30 = 30 * 24 * 60 ## Number of minutes in 30 days
        for month in months_used:
            if month not in self.final_df.index.get_level_values(1):
                raise ValueError(f"Month {month} not found in open contracts data.")
        if len(months_used) == 2:
            T1 = self.final_df.loc[self.time_i, months_used[0]]['tte_yr']
            T2 = self.final_df.loc[self.time_i, months_used[1]]['tte_yr']
            σ2_1 = self.final_df.loc[self.time_i, months_used[0]]['σ^2']
            σ2_2 = self.final_df.loc[self.time_i, months_used[1]]['σ^2']
            MT1 = self.final_df.loc[self.time_i, months_used[0]]['tte_mins']
            MT2 = self.final_df.loc[self.time_i, months_used[1]]['tte_mins']
            normal_case = 100 * np.sqrt(
                    (
                    (T1 * σ2_1) * ( (MT2-NT30) / (MT2-MT1) )
                    +
                    (T2 * σ2_2) * ( (NT30-MT1) / (MT2-MT1) )
                    ) * (365/30)
                )
            special_case = 100 * ( np.sqrt(σ2_1))
            special_condition = MT1 >= NT30

            if special_condition:
                self.vix_value = special_case
            else:
                self.vix_value = normal_case

        return self.vix_value


