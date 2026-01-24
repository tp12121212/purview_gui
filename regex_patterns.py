# Generated from regex_patterns.json for consistent formatting.
# Patterns use raw double-quoted strings unless a trailing backslash requires a normal string.
patterns = [
    {
        'name': 'auspost_tracking',
        'pattern': r"(?:^|[\s,;:\(\)\[\]\"\'\'])((EBA|EA|LP|33|62|99)\d{11,20})(?:$|[\s,;:\(\)\[\]\"\'\']|\.\s|\.$)",
    },
    {
        'name': 'qld_drivers_license_number',
        'pattern': r"(?is)\bLICEN[CS]E\b[\s\S]{0,80}?\b(?:NO\.?|NO|NUMBER|#)?\b[\s\S]{0,40}?(\d{3}\s\d{3}\s\d{3})[\s\S]{0,200}?queensland"
    },
    {
        'name': 'australia_passport_number_latest',
        'pattern': r"(?i)DOCUMENT[\s\S]{0,200}(?:P[A-E]|RA|N|M)[0-9]{7}|(?:P[A-E]|RA|N|M)[0-9]{7}[\s\S]{0,200}DOCUMENT",
    },
    {
        'name': 'nsw_drivers_licence_number_context',
        'pattern': r"(?is)\bWALES\b[\s\S]{0,300}?(\d\s\d{3}\s\d{3}\s\d{3})[\s\S]{0,300}?\bNSW\b",
    },
    {
        'name': 'australia_passport_number_latest',
        'pattern': r"(?i)(?:\b(?:DOCUMENT(?:\s*(?:NO|NUMBER))?|PASSPORT(?:\s*(?:NO|NUMBER))?)\b[\s\S]{0,200}\b(?:P[A-E]|RA|N|M)\d{7}\b|\b(?:P[A-E]|RA|N|M)\d{7}\b[\s\S]{0,200}\b(?:DOCUMENT(?:\s*(?:NO|NUMBER))?|PASSPORT(?:\s*(?:NO|NUMBER))?)\b)",
    },
    {
        'name': 'australian_address',
        'pattern': r"(?:^|[\s,;\:\(\)\[\]\"\'])((\d{1,6}\s+[A-Za-z0-9]+\s+(St|Street|Rd|Road|Ave|Avenue|Ct|Court|Crt|Ln|Lane|Blvd|Boulevard|Pl|Place|Terrace|Terr|Cres|Crescent|Dr|Drive|Pde|Parade|Way|Wk|Walk)))(?:$|[\s,\;\:\(\)\[\]\"\']|\.\s|\.$)",
    },
    {
        'name': 'CEP_AzureEmulatorStorageAccountFilter',
        'pattern': r"(?:^|[\s,;:\(\)\[\]\"\'\'])((Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==))(?:$|[\s,;:\(\)\[\]\"\'\']|\.\s|\.$)",
    },
    {
        'name': 'CEP_AzurePublishSettingPasswords',
        'pattern': r"(?:^|[\s,;:\(\)\[\]\"\'\'])((userpwd=\"[a-z0-9]{60}\"))(?:$|[\s,;:\(\)\[\]\"\'\']|\.\s|\.$)",
    },
    {
        'name': 'CEP_AzureServiceBusConnectionString',
        'pattern': r"(?:^|[\s,;:\(\)\[\]\"\'\'])((EndPoint\s{0,2}=\s{0,2}[\x20-\x7F]{1,200}?servicebus\.windows\.net[\x20-\x7F]{1,200}?SharedAccessKey\s{0,2}=\s{0,2}[a-zA-Z0-9/+]{43}=))(?:$|[\s,;:\(\)\[\]\"\'\']|\.\s|\.$)",
    },
    {
        'name': 'CEP_AzureStorageAccountKey',
        'pattern': r"(?:^|[\s,;:\(\)\[\]\"\'\'])((DefaultEndpointsProtocol\s{0,2}=\s{0,2}[\x20-\x7F]{1,200}?AccountKey\s{0,2}=\s{0,2}[a-zA-Z0-9/+]{86}==))(?:$|[\s,;:\(\)\[\]\"\'\']|\.\s|\.$)",
    },
    {
        'name': 'CEP_AzureStorageAccountKeyGeneric',
        'pattern': "\\\\b\\(\\(>\\|\\\\",
    },
    {
        'name': 'CEP_CommonExampleKeywords',
        'pattern': r"(?:^|[\s,;:\(\)\[\]\"\'\'])((contoso|fabrikam|northwind|sandbox|onebox|localhost|127\.0\.0\.1|testacs\.com|s-int\.net))(?:$|[\s,;:\(\)\[\]\"\'\']|\.\s|\.$)",
    },
    {
        'name': 'CEP_PasswordPlaceHolder',
        'pattern': r"(?:^|[\s,;:\(\)\[\]\"\'\'])(((Password|pwd)\s{0,2}=\s{0,2}\*+|(Password|pwd)=<[a-zA-Z0-9\*\-\_\s]{1,200}>))(?:$|[\s,;:\(\)\[\]\"\'\']|\.\s|\.$)",
    },
    {
        'name': 'CEP_SQLServerConnectionString',
        'pattern': r"(?:^|[\s,;:\(\)\[\]\"\'\'])(((User Id|User ID|uid|UserId)[\x20-\x7F]{1,200}(Password|[^a-z]pwd)=[^$%>@\";\[\{][^;/\"]{7,128}(;|\")))(?:$|[\s,;:\(\)\[\]\"\'\']|\.\s|\.$)",
    },
 {
        'name': 'Ranker_CSCAN_AZURE0020_0eae114f_baad_4dba_a100_c5b34d217964_60068066_CEP2_0',
        'pattern': "\\(\\?i\\)\\(\\^\\|\\[\\^a\\-z\\]\\)\\(DB_\\[a\\-z\\]\\*\\?NAME\\|initial\\ catalog\\|database\\(name\\)\\?\\)\\(\\\\s\\{0,4\\}=\\\\s\\{0,4\\}\\|\\[\"\\\\",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0020_ServerName_21454193_CEP2_0',
        'pattern': r"(?i)(tcp:)?([a-z\-_0-9:\.]{1,50}(\.database\.azure\.com|\.database(\.secure)?\.windows\.net|\.cloudapp\.net|\.database\.usgovcloudapi\.net|\.database\.chinacloudapi\.cn|\.database\.cloudapi\.de))",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0020_UserName_58870012_CEP2_0',
        'pattern': "\\(\\?i\\)\\(DB_USER\\|user\\ id\\|uid\\|user\\(name\\)\\?\\)\\(\\\\s\\{0,4\\}=\\\\s\\{0,4\\}\\|\\[\"\\\\",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0030_9beb734f_ba2b_452b_b422_589f5ac467ef_43332040_CEP2_0',
        'pattern': r"(?i)Shared(Access(Policy)?Key|SecretValue)\s?=",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0050_Partial_8305ad49_df2a_4e1e_a008_fc63cb1db966_49652976_CEP2_0',
        'pattern': r"(?i)iotHub",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0070_combined_ranker_CEP2_0_17ba94a9_a24c_4c84_a838_22a1c0c192e7_26987408_CEP2_0',
        'pattern': r"(?i)Key|Credential",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0070_combined_ranker_CEP2_0_AccountKey_41560081_CEP2_0',
        'pattern': r"(?i)(Storage)?.?Account.?Key",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0070_combined_ranker_CEP2_0_AccountName_40041277_CEP2_0',
        'pattern': r"(?i)AccountName=([a-z0-9_]+);",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0070_combined_ranker_CEP2_0_d37929c5_be80_4f59_951f_5dc6f21d8892_17911681_CEP2_0',
        'pattern': r"(?i)Account|Storage|Access|Primary[^v]|Secondary[^v]|Blob",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0070_combined_ranker_CEP2_0_Endpoint_24827179_CEP2_0',
        'pattern': r"(?i)Endpoint=(https?://[a-z0-9_]{3,50}\.(table|blob|queue|file)\.[a-z0-9\.]{10,50})/?;",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0070_combined_ranker_CEP2_0_EndpointSuffix_64844482_CEP2_0',
        'pattern': r"(?i)^\Wcore\.windows\.net",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0070_EndpointSuffix_22118023',
        'pattern': "\\(\\?i\\)EndpointSuffix=\\(\\[a\\-z0\\-9\\._\\]\\{10,50\\}\\)\\[;\"\\\\",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0080_AccountEndpoint_38496415',
        'pattern': "\\(\\?i\\)AccountEndpoint=\\(https\\?://\\[a\\-z0\\-9_\\.\\]\\+\\\\\\.documents\\\\\\.azure\\\\\\.com\\(:\\\\d\\+\\)\\?\\)/\\?\\[;\"\\\\",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0080_Partial_1eb5757c_210e_46a5_876e_b0ad231103e9_10923418_CEP2_0',
        'pattern': r"(?i)(Doc(ument)?|cosmos)Db(Conn(ection)?Str(ing)?|(Access)?Key)",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0090_b08f98f2_d980_4598_814b_67c29887ebff_33624151_CEP2_0',
        'pattern': r"userPWD=",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0130_AzureBatch_a5d6121e_e9af_4b7d_a7da_9aad47e4c66d_53046711_CEP2_0',
        'pattern': r"(?i)batch\.azure\.com",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0130_Prefix_a853ad91_d200_41b2_8dc4_4ce41dda3b81_3056034_CEP2_0',
        'pattern': r"(?i)((SharedAccess(Policy)?|SAS|Primary|Secondary)Key|SharedAccessSignature|SharedKey)[ -~]{0,50}$",
    },
    {
        'name': 'Ranker_CSCAN_AZURE0140_RefreshToken_74aa94f2_34ed_40bf_ba88_0bc17398a9cf_9381496_CEP2_0',
        'pattern': r"(?i)\Wrefresh.?token",
    },
    {
        'name': 'Ranker_CSCAN_GENERAL0030_ServerName_53517805',
        'pattern': "\\(\\?i\\)\\(\\^\\|\\[\\^a\\-z\\]\\)\\(\\(Remote\\ \\?LU\\(\\ \\?Alias\\)\\?\\|host\\(name\\)\\?\\|data\\ source\\|server\\|addr\\|\\(network\\ \\)\\?address\\)\\(\\\\s\\{0,4\\}=\\\\s\\{0,4\\}\\|:\\\\s\\{0,4\\}\\[\"\\\\",
    },
    {
        'name': 'Scanner_SymmetricKey128_SymmetricKey_61027830_CEP2_0',
        'pattern': r"\(\?i\)\[\^\\w/\\\+\\\._\$,\\\]\(\[a\-z0\-9/\\\+\]\{22\}==\)\(\[\^\\w/\\\+\\\.\$\]\|\$\)",
    },
    {
        'name': 'Scanner_SymmetricKey360_SymmetricKey_31201899_CEP2_0',
        'pattern': r"\(\?i\)\[\^\\w/\\\+\\\.\\\-\$,\\\]\(\[a\-z0\-9/\\\+\]\{60\}\)\[\^\\w/\\\+\\\.\\\-\$,\\\]",
    }
]
