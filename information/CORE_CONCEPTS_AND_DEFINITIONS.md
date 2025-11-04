# Core Concepts and Definitions:

The purpose of this page is to provide definitions and explanations of key terms and concepts related to this project.

## Emissions and Emissions Factors

??? info "Emission factors"
    **Definitions:**
        - "An emission factor gives the relationship between the amount of a pollutant produced and the amount of raw material processed or burnt. For example, for mobile sources, the emission factor is given in terms of the relationship between the amount of a pollutant that is produced and the number of vehicle miles travelled. By using the emission factor of a pollutant and specific data regarding quantities of materials used by a given source, it is possible to compute emissions for the source. This approach is used in preparing an emissions inventory." [DEFRA](https://uk-air.defra.gov.uk/air-pollution/glossary.php?glossary_id=25)
        - "An emission factor (EF) is a coefficient that describes the rate at which a given activity releases greenhouse gases (GHGs) into the atmosphere. They are also referred to as conversion factors, emission intensity and carbon intensity." [Climatiq](https://www.climatiq.io/docs/guides/understanding/what-is-an-emission-factor)

    **Notes:** This factor can vary on a number of factors including but not limited to the specific technology used, age and condition of a technology, the specific chemical properties of a given type of fuel. To illustrate the affect of the technology, take for example a coal-fired generator that is 30 years old. This generator will probably be less efficient than one that is 5 years old, and require more fuel to produce the same amount of electricity. More coal consumed in this scenario means more carbon and emissions per kWh. There can also be differences within the same category of fuel. For example bituminous coal generally has a higher heat content than [lignite](https://www.eia.gov/energyexplained/coal), and the overall footprint of carbon from natural gas may will vary based on its [source](https://www.eia.gov/energyexplained/natural-gas/) or [mixture](https://www.carbonbrief.org/whats-the-difference-between-natural-gas-liquid-natural-gas-shale-gas-shale-oil-and-methane-an-oil-and-gas-glossary/)


??? info "Average Emissions"
    **Definition:** The total carbon emissions per amount of electricity produced by all generators in a system. [ADG Efficiency](https://adgefficiency.com/energy-basics-average-vs-marginal-carbon-emissions/)

    **Notes:** Average emissions are good for analysing environmental impact in the aggregate - over a year or over a large area. Using average emission factors helps simplify the calculations by providing a single value to represent the emissions from a system that contains a diverse set of power generation sources.


??? info "Marginal Emissions"
    - **Definition:** "Marginal emissions refer to the amount of greenhouse gases or other pollutants emitted per unit of energy generated or consumed by the last power plant brought online or taken offline to meet fluctuating demand." [Powerledger](https://powerledger.io/media/marginal-emissions-what-you-need-to-know/)

    - **Notes:** To borrow from logistics and transportation - you can think of marginal emissions as analogous to the 'last mile' that your Amazon delivery takes on a shipment. Before getting to its final destination, there were likely a few different cargo ships, maybe rail cars or semi-trucks that carried your package before it was handed off to a local post office to be delivered. The cargo ship, train, and truck were all likely taking those routes regardless of your action to order this package. But the journey to your home to deliver the package was is a result directly caused by your action to order that package. Similarly, marginal emissions are the emissions associated with the last or next unit of electricity generated to meet demand (deliver your package in this analogy).

    - **Characteristics of Marginal Emissions:**
        - The marginal generator is likely to be the most expensive generator at that time. (It may not be if the plant needs to be kept on for technical reasons). As renewables are characterized by low marginal costs, they are the ones that are unlikely to be pushed off the grid. [ADG Efficiency](https://adgefficiency.com/energy-basics-average-vs-marginal-carbon-emissions/)
        - **Additional sources:** [DESNZ](https://assets.publishing.service.gov.uk/media/66c85e891f215d9f0a913536/guidance-on-valuation-of-energy-use-ghg-emissions-background-documentation.pdf), [Electricity Maps](https://www.electricitymaps.com/content/marginal-emissions-what-they-are-and-when-to-use-them), [Lane Clark & Peacock LLP](https://assets.publishing.service.gov.uk/media/5a7dacfde5274a5eaea65a89/MEF_Analysis_-_Report_FINAL.pdf)


??? info "When to use Average Emissions & Marginal Emissions"
    - Average emissions are useful for understanding the overall impact of a power generation system and for long-term planning and policy-making. They provide a broad view of emissions across all generators in a system.
    - Marginal emissions are more relevant for understanding the impact of specific actions or changes in electricity consumption, such as shifting demand to different times of the day or adding new renewable energy sources. They help identify the emissions associated with the next unit of electricity generated or consumed.
    - "The scientific consensus is clear: marginal emissions rates are the appropriate metric to use for measuring the consequential impact of load shifting, siting new loads, and building new renewables." [WattTime](https://watttime.org/data-science/data-signals/average-vs-marginal/)


## Energy and the Grid

??? info "Baseload Power"
    - **Definition:** The amount of power made available by an energy producer (such as a power plant) to meet fundamental demands by consumers. [Merriam-Webster](https://www.merriam-webster.com/dictionary/baseload)

??? info "Demand Response"
    - **Definitions:**
        - "The changes in electric usage by end-use customers from their normal consumption patterns in response to changes in the price of electricity over time."
        - "The incentive payments designed to induce lower electricity use at times of high wholesale market prices or when system reliability is jeopardized."
    - **Notes:**
        - It "includes all intentional modifications to consumption patterns of electricity of end use customers that are intended to alter the timing, level of instantaneous demand, or the total electricity consumption."
    - **Source:** [IEEE](http://ieeexplore.ieee.org/document/4275494/)

??? info "Grid Energy Storage"
    - **Definition:** The technologies that are connected to the electrical power grid that store energy for later use (e.g. pumped-storage hydroelectricity, Vehicle to Grid, Batteries).
    - **Purpose:** These systems help balance supply and demand by storing excess electricity from variable renewables such as solar and inflexible sources like nuclear power, releasing it when needed.
    - **Source:** [Wikipedia](https://en.wikipedia.org/wiki/Grid_energy_storage)

??? info "Load Balancing"
    - **Definition:** Load Balancing refers to the processes and techniques used to store extra power during periods with lower demand, and then release that power during periods of high demand. The aim is for the power supply system to have a load factor of 1. [Wikipedia](https://en.wikipedia.org/wiki/Load_balancing_(electrical_power))
    - For more information on load factors see [Electrical Rates: The Load Factor and the Density Factor](https://doi.org/10.2307/1885236)
    - Also known as *load matching* or *daily peak demand reserve*

??? info "Locational Marginal Pricing (LMP)"
    - **Definition:** A pricing mechanism used in electricity markets to determine the cost of delivering electricity at specific locations, taking into account the cost of generation and the constraints of the transmission network.
    - The marginal price of electricity at a specific location (node) in the power grid, reflecting the cost of supplying the next increment of electricity demand at that location, considering generation costs and transmission constraints.
    - **Purpose:** LMP helps to ensure that electricity prices reflect the true cost of supplying power, including the impact of congestion and losses in the transmission system.
    - **Sources:** [UKERC](https://ukerc.ac.uk/news/locational-marginal-pricing/), [ISO-NE](https://www.iso-ne.com/participate/support/faq/lmp), [Enverus](https://www.enverus.com/blog/an-intro-to-locational-marginal-pricing/)

??? info "Peak Hours"
    - **Definition:** The hours in a day when people generally consume more electricity due to their daily routine such as getting ready for work in the morning or making dinner in the evening.
    - **Notes:** Peak hours usually occur in the morning or late afternoon/evening  (depending on location).
        - In temperate climates - the peak is usually when household appliances are heavily used in the evening after work hours.
        - In hot climates - the peak is usually late afternoon when the AC load is high - also workplaces are still open and consuming power.
        - In cold climates - the peak may be in the morning when the space heating and industry are both starting up.
    - **Sources:** [Wikipedia](https://en.wikipedia.org/wiki/Peaking_power_plant), [British Gas](https://www.britishgas.co.uk/energy/guides/off-peak-electricity.html)


??? info "Peaking Power Plants"
    **Definition:** The power plants that only run (or mainly run ) when there is a high demand. Because they only supply power occasionally - their power is usually more expensive per kilowatt hour than the base load.

    **Notes:**
        - These plants are different than the base load power plants - which are those that supply a dependable and consistent amount of electricity.
        - Certain peaker plants may operate a few hours a day, or others only a few hours a year.
        - Common peaker plants are  gas turbines or gas engines that burn natural gas - though some burn biogas or other petroleum derivations.
            - Their efficiency is generally 20-42% for simple ones, and 30-42% for newer ones.
            - The New York Power Authority (NYPA) is looking to replace gas peaker plants with battery storage. Ventura County in California was able to do this with Tesla Megapacks, and in Lessines, Belgium 40 Megapacks replaced a turbojet generator.

    **Source:** [Wikipedia](https://en.wikipedia.org/wiki/Peaking_power_plant)

    Also known as *peakers* or *peaker power plants*


## Economics

??? info "Marginal Cost"
    **Definition:** The cost of producing one additional unit of a good or service. It is a key concept in economics and is used to analyze the behavior of firms in competitive markets.[Investopedia](https://www.investopedia.com/terms/m/marginalcostofproduction.asp)


??? info "(Average) Treatment effect"
    - **Definitions:**
        - The "average causal effect of a binary variable on an outcome variable of scientific or policy interest." [MIT](https://economics.mit.edu/sites/default/files/publications/Treatment%20Effects.pdf)
        - A "measure used to estimate the causal effect of a treatment or intervention on an outcome." [CausalWizard](https://causalwizard.app/inference/article/ate)


## Data Science / Mathematics

??? info "Greedy Algorithm"
    **Definition:** A problem-solving heuristic that makes the locally optimal choice at each stage with the hope of finding a global optimum. [Geeks for Geeks](https://www.geeksforgeeks.org/dsa/greedy-algorithms/)


??? info "Ordinary Least Squares Regression (OLS)"
    **Definition:** A technique for estimating the coefficients of a linear regression equation by minimizing the sum of the squared differences between the observed and predicted values. [XLSTAT](https://www.xlstat.com/solutions/features/ordinary-least-squares-regression-ols)
        - Y = β0 + Σj=1..p βjXj + ε


## Coding Libraries

??? info "SQLAlchemy"

    - SQLAlchemy is a Python database toolkit - essentially the bridge between Python and SQL databases.
    It provides a set of high-level API's to interact with databases, allowing you to write Python code that can create, read, update, and delete data in a database.

    - **Core Aspects:**
        - *create_engine* : This is the core function that creates a new SQLAlchemy engine instance, stores the information needed to connect to the database, and establishes that connection.
            - It takes a database URL as an argument, which specifies the database dialect (e.g., PostgreSQL), username, password, host, port, and database name.
            - The URL format is: dialect+driver://username:password@host:port/database
        - *inspect* : The inspect function is used to create an inspector object, which can be used to get information about the database schema including:
            - schema names in the database
            - table names in the schemas
            - column names and data types for tables
            - foreign key relationships
            - This object usually retrieves the information from the information_schema system table, but just wraps the SQL queries into a more user-friendly interface.
        - *text* : The text function is used to safely wrap SQL strings and create a text object which is then passed and its contained queries executed.

    - Importing SQLAlchemy ORM libraries - the Object Relational Mapper (ORM) is a way to interact with the database using Python objects instead of SQL queries.
    It automatically maps database tables to Python classes, table columns to class attributes, and table rows to Python objects.
    It allows you to interact with the database using Python code instead of writing raw SQL queries.

    - [Documentation](https://docs.sqlalchemy.org/en/20/)
