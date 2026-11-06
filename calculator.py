import pandas
from pathlib import Path
import datetime
import csv
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from typing import Literal
import math
import plot_total_costs as costplot

class Case:
    def __init__(self, data_file: str, nominal_capacity: float, resolution: Literal["Hourly", "Quarterly", "Decimaly", "Minute"], utilization:float, power_factor:float | list[tuple[datetime.datetime, float]]):
        """
        Creates a Case object used during simulations.
        It allows for multiple cases to be created and tested in Series/Parallel.

        The constructor will first collect the essential information, after which the data will be read and pre-processed.

        :param str data_file: data file path.
        :param float nominal_capacity: Site's nominal capacity in MegaWatts.
        :param Literal["Hourly", "Quarterly", "Decimaly", "Minute"] resolution: Resolution of the simulation in 60, 15, 10 or 1 minute increments.
        :param float utilization: utilization of the charging site (0-100%).
        :param float | list[tuple[datetime.datetime, float]] power_factor: defines the power factor for the site.
        """

        self.Resolution = {"Hourly": 1, "Quarterly": 4, "Decimaly": 6, "Minute": 60}[resolution]
        if utilization <= 1:
            self.Utilization = utilization
        else:
            raise Exception("Utilization cannot surpass 100%.")
        self.Power_factor = power_factor
        self.Nominal_Capacity = nominal_capacity * 1000 # kW; [3, 5, 10] MW for now. possibly dynamic for future research
        self.Energy_Consumption = self.__Energy_Consumption_Preprocessing(data_file, self.Nominal_Capacity, utilization) # data: search for the values per iteration or pre-calculate the values for each timestep before the simulation?
                                    ## for this case, let's pre-calculate the values. with real data, the energy consumption values are provided in csv format
        
        self.Reactive_Power = self.__Reactive_Power_Preprocessing(self.Energy_Consumption, power_factor)
        self.Reactive_Power_peak = max(self.Reactive_Power, key=lambda x: x[1])

        self.Reactive_power_output = self.Reactive_Power[::2] # tuple (datetime.datetime, float) -> Capacitive Power Factor (anto)
        self.Reactive_power_input = self.Reactive_Power[:-1] # tuple (datetime.datetime, float) -> Inductive Power Factor (otto)
        self.Peak_power = self.Nominal_Capacity * utilization

    def __Energy_Consumption_Preprocessing(self, data: str, nominal_capacity: float, utilization: float) -> list[tuple[datetime.datetime, float]]:
        """
        Private Method: Only accessed inside the Class

        Converts data from the data file into the case data.

        First extracts utilization from the plot (Otteny et al. 2023)
        -
        Normalizes the data -> 0-1.00 utilization
        -
        Transforms the utilization into charging power -> 0.5 * Nominal power * Peak site utilization
        -
        Interpolates data between data points and returns daily utilization data in {resolution} increments.
        """
        filepath = data
        csv_path = Path(filepath)
        df = pandas.read_csv(csv_path, delimiter=", ", encoding='utf-8', keep_default_na=False)

        ## Probabilities file -> site utilization
        times_df = df['x'].tolist()
        probabilities_df: list = df['y'].tolist()
        peak = max(probabilities_df)

        times: list[list] = []

        # str -> datetime
        # Normalizes the data, eg. 0-0.33 -> 0-1
        for i in range(len(times_df)):
            t = datetime.datetime.strptime(f"{math.floor(times_df[i])}:{math.floor((times_df[i] - math.floor(times_df[i]))*60)}", "%H:%-M")
            #p = round(float(probabilities_df[i]/peak), 3) if probabilities_df[i] >= 0 else 0
            p = round(abs(float(probabilities_df[i]/peak*(2/3))), 4)
            times.append([t, p])

        sorted_times = sorted(times, key=lambda x: x[0])

        # Data start time -> 00:00:00.000 (default date -> 01.01.1900; but irrelevant)
        start_time = datetime.datetime.strptime("00", "%H")
        pre_processed = []
        for i in range(24*self.Resolution):
            time = start_time + datetime.timedelta(minutes=60/self.Resolution * i)

            # Interpolation of data
            for step in range(len(sorted_times)):
                if ((time.time() >= sorted_times[step - 1][0].time())
                                ^ (time.time() < sorted_times[step][0].time())
                                ^ (sorted_times[step - 1][0].time() < sorted_times[step][0].time())
                                ):
                    
                    x_0 = (sorted_times[step - 1][0] - start_time).seconds if step != 0 else 0
                    x_1 = (sorted_times[step][0] - start_time).seconds
                    y_0 = sorted_times[step - 1][1]
                    y_1 = sorted_times[step][1] 

                    x = ((time - start_time).seconds)

                    # m = (sorted_times[step - 1][1] - sorted_times[step][1].time()) / ((sorted_times[step - 1][0].time() - sorted_times[step][0].time()).seconds)
                    # b = sorted_times[step - 1][1] / (m * (start_time - sorted_times[step - 1][0].time()).seconds)
                    y_interpolated =  (y_0 * (x_1 - x) + y_1 * (x - x_0)) / (x_1 - x_0)

                    pre_processed.append((time, y_interpolated))

        pre_processed = sorted(pre_processed, key=lambda x: x[0])

        def integral(data):
            dt = 1 / (24 * self.Resolution) # simulation timestep for a datasource with one-day temporal dimension
            return sum(p[1] * dt for p in data)

        default_usage = integral(pre_processed)
        print(f"""Default usage: {default_usage}""")
        peak = max(pre_processed, key=lambda x: x[1])[1]
        peak_usage = default_usage / peak
        scale = min(utilization, peak_usage) / default_usage

        # if utilization != peak_usage:
        #     energy = []
        #     for time, p in pre_processed:
        #         energy.append((time, (p * scale))) 

        #     usage = integral(energy)
        #     print(f"""Current usage: {usage}""")
        #     if usage == utilization:
        #         print("Usage correctly set.")
        #     else:
        #         print("Current")

        if utilization > peak_usage:
            dilation = math.log(utilization)/math.log(peak_usage) # U(x) = ∫f(t)^x <=> x = log(U)/log(∫f(t))
            
            energy = []
            for time, p in pre_processed:
                energy.append((time, ((p * scale) ** dilation * nominal_capacity))) 

            usage = integral(energy)
            print(f"""Current usage: {usage}""")
            if usage == utilization:
                print("Usage correctly set.")
            else:
                print("Current")
            return energy
        else:
            energy = []
            for time, p in pre_processed:
                energy.append((time, (p * scale) * nominal_capacity)) 

            usage = integral(energy)
            print(f"""Current usage: {usage}""")
            if usage == utilization:
                print("Usage correctly set.")
            else:
                print("Current")

            return energy

    def __Reactive_Power_Preprocessing(self, energy_consumption: list[tuple[datetime.datetime, float]], power_factor: float | list[tuple[datetime.datetime, float]]) -> list[tuple[datetime.datetime, float, float]]:
        reactive = []

        # Data start time -> 00:00:00.000 (default date -> 01.01.1900; but irrelevant)
        start_time = datetime.datetime.strptime("00", "%H")
        if type(power_factor) == float:
            for step in energy_consumption:
                r = (
                    step[0],
                    step[1] * math.tan(math.acos(abs(power_factor))) if power_factor > 0 else 0, # Inductive Power Factor (otto)
                    step[1] * math.tan(math.acos(abs(power_factor))) if power_factor < 0 else 0 # Capacitive Power Factor (anto)
                )
                
                reactive.append(r)
        elif type(power_factor) == list:
            
            for step in energy_consumption:
                time: datetime.datetime = step[0]
                for i in range(len(power_factor)):
                    time_0: datetime.datetime = power_factor[i - 1][0]; factor_0 = power_factor[i - 1][1]
                    time_1: datetime.datetime = power_factor[i][0]; factor_1 = power_factor[i][1]

                    if ((time.time() >= time_0.time())
                        ^ (time.time() < time_1.time())
                        ^ (time_0.time() < time_1.time())
                        ):

                        x_0 = (time_0 - start_time).seconds if step != 0 else 0
                        x_1 = (time_1 - start_time).seconds
                        y_0 = factor_0
                        y_1 = factor_1

                        x = ((time - start_time).seconds)
                        
                        factor_interpolated =  (y_0 * (x_1 - x) + y_1 * (x - x_0)) / (x_1 - x_0)
                        
                        r = (
                            step[0],
                            step[1] * math.tan(math.acos(abs(factor_interpolated))) if factor_interpolated > 0 else 0, # Inductive Power Factor (otto)
                            step[1] * math.tan(math.acos(abs(factor_interpolated))) if factor_interpolated < 0 else 0 # Capacitive Power Factor (anto)
                        )
                        
                        reactive.append(r)
        return reactive

class DSO:
    def __init__(self, df: pandas.DataFrame, Company_number: int, Name: str, Pricing_available: bool, Battery_storage_available: bool, Distribution_fee_details: str = "", Number_distribution_fee: int = 1, Battery_storage_details: str = "", Number_battery_storage: int = 0) -> None:
        """
        Creates a DSO object for each DSO.

        The constructor will first collect the essential information, after which the different pricing schemes can be defined.

        :param df: Raw data.
        :param int Company_number: Distribution company number (from the spreadsheet).
        :param str Name: Distribution System Operator (DSO).
        :param bool Pricing_available: Pricing found? (True/False).
        :param bool Battery_storage_available: Battery storage pricing available? (True/False).
        :param str Distribution_fee_details: Details about this pricing product? -> None.
        :param int Number_distribution_fee: How many pricing schemes? -> 1.
        :param str Battery_storage_details: Details about this pricing product? -> None.
        :param int Number_battery_storage: How many pricing schemes?
        """

        self.Company_number = Company_number
        self.Name = Name
        self.Pricing_available = Pricing_available
        self.Battery_storage_available = Battery_storage_available
        self.Distribution_fee_details = Distribution_fee_details
        self.Number_distribution_fee = Number_distribution_fee
        self.Battery_storage_details = Battery_storage_details
        self.Number_battery_storage = Number_battery_storage
        self.Schemes = {"Distribution": [], "Storage": []}
        self.Costs = []

        self.__Define_Distribution_Pricing_Scheme(df)
        
        if Number_battery_storage != None:
            self.__Define_Battery_Storage_Pricing_Scheme(df)

    def __String_to_Datetime_Parser(self, type: str, scheme: int, filter: list[str], options: int) -> None:
        """
        Private Method: Only accessed inside the Class

        Object function to define the pricing option filters for the specific DSO.
        """

        year = 2026
        periods: list[list[str]] = []
        for i in range(1, options + 1):
            for string in filter:
                if self.Schemes[type][scheme][f"{string}_option_{i}"] != "-":
                    periods.append([f"{string}_option_{i}", self.Schemes[type][scheme][f"{string}_option_{i}"]])

        parsed = []
        for p in periods:
            if p[1] == "All times":
                parsed.append([p[0], None])
                continue

            elif p[1] != "Other times":
                text = p[1]
                filters = text.strip("- ").split(" ")
                filters_parsed = []

                for i in filters:
                    try:
                        filters_parsed.append(["date", datetime.datetime.strptime(f"{i}{year}", "%-d.%m.%Y")])
                        continue
                    except: pass

                    try:
                        filters_parsed.append(["weekday", datetime.datetime.strptime(f"{year}-{00}-{i.capitalize()}", "%Y-%W-%A")])
                        continue
                    except: pass

                    try:
                        filters_parsed.append(["time", datetime.datetime.strptime(f"{year}-{i}", "%Y-%-H:%M")])
                        continue
                    except: pass

                parsed.append([p[0], filters_parsed])
            else:
                parsed.append([p[0], None])
                continue
        
        self.Schemes[type][scheme] = [parsed, self.Schemes[type][scheme]]

    def __Define_Distribution_Pricing_Scheme(self, df: pandas.DataFrame) -> None:
        """
        Private Method: Only accessed inside the Class

        Object function to define the distribution pricing scheme for the specific DSO.
        """
        index = 0
        for i, values in df["Distribution company number"].items():
            if values == self.Company_number:
                index = hash(i)
                break

        self.Schemes["Distribution"] = []
        for i in range(self.Number_distribution_fee):
            scheme = {}
            
            scheme["base_price"] = float(df["Distribution fee - base price ( /month, VAT 0%)"][index + i]) if df["Distribution fee - base price ( /month, VAT 0%)"][index + i] not in ["#N/A", "-"] else None #float €/month, VAT 0%
            scheme["transfer_option_1"] = df["Distribution fee - electricity transfer option 1"][index + i] #str, datetime
            scheme["transfer_option_1_price"] = float(df["Distribution fee - transfer price ( /kWh)"][index + i]) if df["Distribution fee - transfer price ( /kWh)"][index + i] not in ["#N/A", "-"] else None #float €/kWh, VAT 0%
            scheme["transfer_option_2"] = df["Distribution fee - electricity transfer option 2"][index + i] #str, datetime
            scheme["transfer_option_2_price"] = float(df["Distribution fee - transfer price 2 ( /kWh)"][index + i]) if df["Distribution fee - transfer price 2 ( /kWh)"][index + i] not in ["#N/A", "-"] else None #float €/kWh, VAT 0%
            scheme["transfer_option_3"] = df["Distribution fee - electricity transfer option 3"][index + i] #str, datetime
            scheme["transfer_option_3_price"] = float(df["Distribution fee - transfer price 3 ( /kWh)"][index + i]) if df["Distribution fee - transfer price 3 ( /kWh)"][index + i] not in ["#N/A", "-"] else None #float €/kWh, VAT 0%
            scheme["transfer_option_4"] = df["Distribution fee - electricity transfer option 4"][index + i] #str, datetime
            scheme["transfer_option_4_price"] = float(df["Distribution fee - transfer price 4 ( /kWh)"][index + i]) if df["Distribution fee - transfer price 4 ( /kWh)"][index + i] not in ["#N/A", "-"] else None #float €/kWh, VAT 0%
            scheme["details_reactive_power"] = df["Distribution fee - Details for reactive power?"][index + i] #str
            scheme["transfer_otto"] = float(df["Distribution fee - reactive power, otto ( /kVAr,month, VAT 0%)"][index + i]) if df["Distribution fee - reactive power, otto ( /kVAr,month, VAT 0%)"][index + i] not in ["#N/A", "-"] else None #float €/kVAr/month, VAT 0%
            scheme["transfer_anto"] = float(df["Distribution fee - reactive power, anto ( /kVAr,month, VAT 0%)"][index + i]) if df["Distribution fee - reactive power, anto ( /kVAr,month, VAT 0%)"][index + i] not in ["#N/A", "-"] else None #float €/kVAr/month, VAT 0%
            scheme["power_tariff_available"] = df["Distribution fee - Is ther a power tariff? (TRUE / FALSE)"][index + i] == "TRUE" #bool
            scheme["details_power_tariff"] = df["Distribution fee - How the power tariff is defined?"][index + i] #str
            scheme["minimum_power"] = float(df["Distribution fee - Minimum power to charge (kW)"][index + i]) if df["Distribution fee - Minimum power to charge (kW)"][index + i] not in ["#N/A", "-"] else None #float kW
            scheme["power_tariff"] = float(df["Distribution fee - Power tariff ( /kW, month, VAT 0%)"][index + i]) if df["Distribution fee - Power tariff ( /kW, month, VAT 0%)"][index + i] not in ["#N/A", "-"] else None  #float €/kW/month, VAT 0%

            self.Schemes["Distribution"].append(scheme)

            self.__String_to_Datetime_Parser("Distribution", i, ["transfer"], 4)  

    def __Define_Battery_Storage_Pricing_Scheme(self, df: pandas.DataFrame) -> None:
        """
        Private Method: Only accessed inside the Class

        Object function to define the battery storage pricing scheme for the specific DSO.
        """

        index = 0
        for i, values in df["Distribution company number"].items():
            if values == self.Company_number:
                index = hash(i)
                break

        self.Schemes["Storage"] = [] 
        for i in range(self.Number_battery_storage):
            scheme = {}
            
            scheme["difference_demand_supply"] = df["Battery storage - different pricing for demand and supply? (TRUE / FALSE)"][index + i] == "TRUE" #bool
            scheme["pricing_type"] = df["Battery storage - pricing type (demand / supply / both)"][index + i] #str (demand / supply / both)
            scheme["storage_base_price"] = df["Battery storage - base price ( /month)"][index + i] #float €/month
            scheme["storage_power_tariff_details"] = df["Battery storage - How the power tariff is defined?"][index + i] #str
            scheme["storage_power_tariff"] = df["Battery storage - power tariff ( /kW, month)"][index + i] #float €/kW/month
            scheme["storage_anto"] = df["Battery storage - reactive power, anto ( /kVAr, month)"][index + i] #float €/kVAr/month
            scheme["storage_otto"] = df["Battery storage - reactive power, otto ( /kVAr, month)"][index + i] #float €/kVAr/month
            scheme["storage_details"] = df["Battery storage - other details?"][index + i] #str
            scheme["storage_reactive_energy"] = df["Battery storage - Reactive energy, anto ( /kVArh)"][index + i] #float €/kVArh
            #scheme["storage_transfer_pricing_scheme"] = df["Battery storage - Electricity tranfer pricing scheme"][index + i] #str, datetime
            scheme["storage_transfer_option_1"] = df["Battery storage - Electricity transfer option 1"][index + i] #str, datetime
            scheme["storage_transfer_option_1_price"] = df["Battery storage - Electricity transfer price ENERGIA-/KUORMITUSMAKSU OTTO ( /kWh, VAT 0 %)"][index + i] #float €/kWh, VAT 0%
            scheme["storage_transfer_option_2"] = df["Battery storage - Electricity transfer option 2"][index + i] #str, datetime
            scheme["storage_transfer_option_2_price"] = df["Battery storage - Electricity transfer price 2 ENERGIA-/KUORMITUSMAKSU OTTO ( /kWh, VAT 0 %)"][index + i] #float €/kWh, VAT 0%
            scheme["storage_consumption_option_1"] = df["Battery storage - Consumption charge option 1"][index + i] #str, datetime
            scheme["storage_consumption_option_1_price"] = df["Battery storage - Consumption charge for own production ENERGIA-/KUORMITUSMAKSU VERKKOON ANTO (cents / kWh, VAT 0 %)"] #float €/cent/kWh, VAT 0%
            scheme["storage_consumption_option_2"] = df["Battery storage - Consumption charge option 2"][index + i] #str, datetime
            scheme["storage_consumption_option_2_price"] = df["Battery storage - Consumption charge 2 for own production ENERGIAMAKSU VERKKOON ANTO (cents / kWh, VAT 0 %)"][index + i] #float €/cent/kWh, VAT 0%
            scheme["storage_fingrid_power_charge"] = df["Battery storage - Fingrid energy storage power charge ( /MW/kk)"][index + i] #float €/MW/month

            self.Schemes["Storage"].append(scheme)

            self.__String_to_Datetime_Parser("Storage", i, ["storage_transfer", "storage_consumption"], 2)



def Simulation(dso: DSO, case: Case, duration: int = 1, start_date = datetime.datetime.today()): # This way, calculations can be executed in parallel for larger simulations

    results = []
    debug = []
    schemeNumber = 0
    # Each scheme simulation is performed separately and appended to dso.Costs -> [[...], [...]] <=> [[scheme_1], [scheme_2]]
    for scheme in dso.Schemes["Distribution"]:
        schemeNumber += 1
        base_price = scheme[1]["base_price"] * 12

        # Temporal range of utilization data = 24 hours -> will not include extra logic on dynamic pricing yet. Check "REACTIVE POWER FEE & POWER TARIFF" section for more detail
        power_tariff = 0

        # Reactive power set to 0 for now, will not include extra logic on dynamic pricing yet. Check "REACTIVE POWER FEE & POWER TARIFF" section for more detail
        reactive_power_fee = 0
        energy_fee = 0

        filters = scheme[0] # Temporal filters. Easiest and more robust way I found to work using all data types. See DSO.__String_to_Datetime_Parser for more details
        pricing = scheme[1] # Pricing associated with the aforementioned filters

        # Finding "Other times" in CSV file.
        filter_list = list(range(len(filters)))
        
        other_times = None
        for i in range(len(filters)):
            if filters[i][1] == None or "":
                other_times = filter_list.pop(i)
                break

        # One year simulation. Can pass duration as a parameter for the function in case the user wants to test longer/shorter periods of time
        for i in range(duration * 8760 * case.Resolution): #full year
            time = start_date + datetime.timedelta(minutes=i * 60 / case.Resolution)

            ## ----------------------------------------- REACTIVE POWER FEE & POWER TARIFF ------------------------------------------ ## -> still doesn't look at historical data as the load profile = 24 hours << 30 days
            # Only charged once per month, at the end of the month
            if time.month != (time + datetime.timedelta(minutes=60 / case.Resolution)).month:
                ## -------------------- REACTIVE POWER FEE --------------------- ##
                for j in range(len(case.Reactive_Power)):
                    if case.Reactive_Power[j][0].time() == time.time():

                        reactive_power_fee += (scheme[1]["transfer_otto"] * case.Reactive_Power_peak[1] #[j][1]  
                                                if scheme[1]["transfer_otto"] != None 
                                                else 0
                                            ) + (
                                                scheme[1]["transfer_anto"] * case.Reactive_Power_peak[2] #[j][2]
                                                if scheme[1]["transfer_anto"] != None
                                                else 0
                                            )

                ## --------------------- POWER TARIFF ------------------------- ##
                power_tariff += scheme[1]["power_tariff"] * case.Peak_power if scheme[1]["power_tariff"] != None else 0

            ## ----------------------------------- ENERGY CONSUMPTION FEE ---------------------------------- ##
            # Defining the energy consumed per resolution interval [60, 15, 10, 1] min <-> [1, 4, 6, 60] resolution (for now)
            Consumption = 0
            for j in case.Energy_Consumption:
                if j[0].time() == time.time(): 
                    Consumption = j[1] / case.Resolution
                    break

            # Skipping intricate logic if only one pricing option is available -> "All times" in CSV/Excel
            if len(filters) == 1:
                energy_fee += pricing["transfer_option_1_price"] * Consumption
                continue

            # Matching the current simulation time to filters, there is a less confusing and faster way to compute this, but this works fine for now. less scalable at finer resolutions
            other = True
            for i in filter_list:
                for j in range(len(filters[i][1]) - 1):
                    match filters[i][1][j][0]:
                        case "date":
                            if filters[i][1][j + 1][0] != "date": continue

                            if filters[i][1][j][1].date() > time.date() and filters[i][1][j + 1][1].date() < time.date(): break
                        case "weekday":
                            if filters[i][1][j + 1][0] != "weekday": continue

                            if filters[i][1][j][1].strftime("%w") > time.strftime("%w") or filters[i][1][j + 1][1].strftime("%w") < time.strftime("%w"): break
                        case "time":
                            if filters[i][1][j + 1][0] != "time": continue

                            if not((time.time() >= filters[i][1][j][1].time())
                                ^ (time.time() < filters[i][1][j + 1][1].time())
                                ^ (filters[i][1][j][1].time()< filters[i][1][j + 1][1].time())): break

                            energy_fee += pricing[f"transfer_option_{i + 1}_price"] * Consumption
                            other = False

                            debug.append([time, f"transfer_option_{i + 1}_price", pricing[f"transfer_option_{i + 1}_price"], energy_fee])
                            break

            # pricing for "Other times"
            if other and other_times != None: 
                energy_fee += pricing[f"transfer_option_{other_times + 1}_price"] * Consumption
                debug.append([time, f"transfer_option_{other_times + 1}_price", pricing[f"transfer_option_{other_times + 1}_price"], energy_fee])


        # Results and debug data sent in tidy packets for main. DSOs with unknown pricing schemes return an empty list -> [] 
        results.append({
            "DSO": dso.Name,
            "Scheme": schemeNumber,
            "base price": base_price,
            "power tariff": power_tariff,
            "reactive power fee": reactive_power_fee,
            "energy fee": energy_fee,
            "total": base_price + power_tariff + reactive_power_fee + energy_fee
        })

    return results, debug

def debugging(data):
    ## Out of order (for now)
    # flow_time = data[:, 0]
    # costs = data[:, -1]
    # x = mdates.date2num(flow_time[:8760])
    
    # plt.style.use('seaborn-v0_8')
    # fig, ax = plt.subplots(figsize=(10, 5))

    # ax.plot_date(x, costs[:8760], '-', label=f'Costs')

    # ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%H:%M'))
    # fig.autofmt_xdate()

    # ax.set_xlabel('Time (DD-hh:mm)')
    # ax.set_ylabel('Temperature (K)')
    # ax.set_title('Core max temperatures vs time')
    # ax.legend()
    # ax.grid(True)
    # fig.tight_layout()
    # fig.savefig("debug.png", dpi=200)
    pass

def main():
    index_list: list[dict[str, int]] = []
    dso_list: list[DSO] = []

    # File reading and preprocessing
    filepath = input("Filepath:\n")
    csv_path = Path(filepath)
    df = pandas.read_csv(csv_path, delimiter=";", encoding='utf-8', keep_default_na=False)

    for index, value in df["Distribution system operator (DSO)"].items():
        if index == 0:
            index_list.append({value: hash(index)})
            continue
        
        if value not in index_list[-1]:
            index_list.append({value: hash(index)})

    # Creating a new DSO object. Basic details are sent to the constructor and deeper filereading and processing is done using private functions inside the class
    for i in index_list:
        dso_list.append(DSO(df=df, 
                            Company_number=df["Distribution company number"][i[list(i)[0]]],
                            Name=df["Distribution system operator (DSO)"][i[list(i)[0]]],
                            Pricing_available=df["Pricing found (TRUE / FALSE)"][i[list(i)[0]]] == "TRUE",
                            Battery_storage_available=df["Battery storage - Battery storage pricing available (TRUE/FALSE)"][i[list(i)[0]]] == "TRUE",
                            Number_distribution_fee=int(df["Distribution fee - How many pricing schemes?"][i[list(i)[0]]]) if df["Distribution fee - How many pricing schemes?"][i[list(i)[0]]] != "#N/A" else 0,
                            Number_battery_storage=int(df["Battery storage - How many pricing schemes?"][i[list(i)[0]]]) if df["Battery storage - How many pricing schemes?"][i[list(i)[0]]] != "#N/A" else 0
                            )
                        )

    # case variable -> input csv filepath, resolution and utilization rate
    Nominal_Capacity = 5 #MW
    utilization = 0.2
    power_factor = 0.98
    case = Case(data_file=input("Filepath:\n"), nominal_capacity=Nominal_Capacity, resolution="Decimaly", utilization=utilization, power_factor=power_factor)

    # Generate charging power curve from the utilization rate
    times = [i / case.Resolution for i in range(len(case.Energy_Consumption))]
    power = [x[1] / 1000 for x in case.Energy_Consumption]
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    ax.plot(times, power, linewidth=2)
    
    ax.set_title(
        f"Charging Station Power Demand\n"
        f"Nominal capacity = {case.Nominal_Capacity/1000:.1f} MW, "
        f"Utilization = {case.Utilization:.0%}"
    )
    
    ax.set_xlabel("Hour of the day (h)")
    ax.set_ylabel("Total power demand (MW)")
    ax.set_xlim(0, 25)
    ax.set_xticks(range(0, 25, 2))
    ax.set_ylim(0, case.Nominal_Capacity / 1000 + 1)
    ax.set_yticks(range(0, int(case.Nominal_Capacity / 1000) + 1, 1))
    
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plot_file = f"charging_profile_nom_power_{case.Nominal_Capacity/1000:.1f}MW_utilization_{case.Utilization:.0%}.png"
    plt.savefig(plot_file, dpi=300)
    plt.show()
    
    for dso in dso_list:
        # debug variable for debugging purposes, uncomment code block "DEBUGGING" for raw CSV data
        results, debug = Simulation(dso=dso, case=case, start_date=datetime.datetime(year=2026, month=1, day=1))
        print(results)

        for result in results: dso.Costs.append(result)

        ## CODE BLOCK: DEBUGGING ##
        # debugging(debug)
        # with open(f'debug_{dso.Name}.csv', 'w', newline='') as f:
        #     writer = csv.writer(f)
        #     writer.writerows(debug)

    results_list = []
    # Exporting results to CSV format. Graphics and plots are performed in another program (for now)
    with open('results_matrix.csv', 'w', newline='', encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["DSO","Scheme","base price","energy fee","power tariff","reactive power fee"])
        for dso in dso_list:
            if len(dso.Costs) == 0: continue
            number = 1

            # Sorting DSO's pricing schemes by costs and only saving the cheapest option
            schemes = sorted(dso.Costs, key= lambda x: x["total"])

            for i in range(len(dso.Costs)):
                writer.writerow([dso.Name, i + 1, dso.Costs[i]["base price"] != 0, dso.Costs[i]["energy fee"] != 0, dso.Costs[i]["power tariff"] != 0, dso.Costs[i]["reactive power fee"] != 0])

            results_list.append(schemes[0])

    # Sending to Plot function
    costplot.plot(results_list, f"dso_scheme_total_cost_comparison_{Nominal_Capacity}MW_{utilization}PP_{power_factor}PF.png")

main()