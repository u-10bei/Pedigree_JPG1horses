-- phpMyAdmin SQL Dump
-- version 4.4.15.10
-- https://www.phpmyadmin.net
--
-- Host: localhost
-- Generation Time: 2022 年 9 月 21 日 10:45
-- サーバのバージョン： 10.5.15-MariaDB-log
-- PHP Version: 5.4.16

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `xs386482_g1horse`
--

-- --------------------------------------------------------

--
-- ビュー用の代替構造 `ForGroup`
--
CREATE TABLE IF NOT EXISTS `ForGroup` (
`FatherId` smallint(6)
,`Horse` varchar(20)
,`Child` bigint(21)
);

-- --------------------------------------------------------

--
-- ビュー用の代替構造 `ForLink`
--
CREATE TABLE IF NOT EXISTS `ForLink` (
`FatherId` smallint(6)
,`Child` bigint(21)
);

-- --------------------------------------------------------

--
-- ビュー用の代替構造 `ForNode`
--
CREATE TABLE IF NOT EXISTS `ForNode` (
`Id` smallint(6)
,`Horse` varchar(20)
,`FatherId` smallint(6)
,`GroupId` smallint(6)
,`GroupName` varchar(20)
,`Power` bigint(22)
);

-- --------------------------------------------------------

--
-- ビュー用の代替構造 `ForNode2`
--
CREATE TABLE IF NOT EXISTS `ForNode2` (
`Id` smallint(6)
,`GroupName` varchar(20)
);

-- --------------------------------------------------------

--
-- ビュー用の代替構造 `ForPower`
--
CREATE TABLE IF NOT EXISTS `ForPower` (
`WinnerId` smallint(6)
,`Win` bigint(21)
);

-- --------------------------------------------------------

--
-- ビュー用の代替構造 `ForStratify`
--
CREATE TABLE IF NOT EXISTS `ForStratify` (
`From` varchar(20)
,`To` varchar(20)
,`Value` bigint(22)
);

-- --------------------------------------------------------

--
-- ビュー用の代替構造 `Link`
--
CREATE TABLE IF NOT EXISTS `Link` (
`From` varchar(20)
,`To` varchar(20)
,`Value` bigint(22)
);

-- --------------------------------------------------------

--
-- ビュー用の代替構造 `Node`
--
CREATE TABLE IF NOT EXISTS `Node` (
`Id` varchar(20)
,`Label` varchar(20)
,`Group` varchar(20)
,`Value` bigint(23)
);

-- --------------------------------------------------------

--
-- テーブルの構造 `Pedigree`
--

CREATE TABLE IF NOT EXISTS `Pedigree` (
  `Id` smallint(6) NOT NULL,
  `Horse` varchar(20) NOT NULL,
  `FatherId` smallint(6) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- テーブルの構造 `Race_Winner`
--

CREATE TABLE IF NOT EXISTS `Race_Winner` (
  `Ryear` smallint(6) NOT NULL,
  `Rtitle` varchar(50) NOT NULL,
  `WinnerId` smallint(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --------------------------------------------------------

--
-- ビュー用の代替構造 `StratifyLink`
--
CREATE TABLE IF NOT EXISTS `StratifyLink` (
`From` varchar(20)
,`To` varchar(20)
,`Value` bigint(22)
,`Power` bigint(22)
);

-- --------------------------------------------------------

--
-- ビュー用の構造 `ForGroup`
--
DROP TABLE IF EXISTS `ForGroup`;

CREATE ALGORITHM=UNDEFINED DEFINER=`xs386482_u10bei`@`localhost` SQL SECURITY DEFINER VIEW `ForGroup` AS select `ForLink`.`FatherId` AS `FatherId`,`Pedigree`.`Horse` AS `Horse`,`ForLink`.`Child` AS `Child` from (`ForLink` join `Pedigree` on(`ForLink`.`FatherId` = `Pedigree`.`Id`)) where `ForLink`.`Child` > 1;

-- --------------------------------------------------------

--
-- ビュー用の構造 `ForLink`
--
DROP TABLE IF EXISTS `ForLink`;

CREATE ALGORITHM=UNDEFINED DEFINER=`xs386482_u10bei`@`localhost` SQL SECURITY DEFINER VIEW `ForLink` AS select `Pedigree`.`FatherId` AS `FatherId`,count(`Pedigree`.`FatherId`) AS `Child` from `Pedigree` group by `Pedigree`.`FatherId` having `Pedigree`.`FatherId` > 0;

-- --------------------------------------------------------

--
-- ビュー用の構造 `ForNode`
--
DROP TABLE IF EXISTS `ForNode`;

CREATE ALGORITHM=UNDEFINED DEFINER=`xs386482_u10bei`@`localhost` SQL SECURITY DEFINER VIEW `ForNode` AS select `Pedigree`.`Id` AS `Id`,`Pedigree`.`Horse` AS `Horse`,`Pedigree`.`FatherId` AS `FatherId`,`ForGroup`.`FatherId` AS `GroupId`,`ForGroup`.`Horse` AS `GroupName`,ifnull(`ForGroup`.`Child`,0) + 1 AS `Power` from (`Pedigree` left join `ForGroup` on(`Pedigree`.`Id` = `ForGroup`.`FatherId`)) where `Pedigree`.`FatherId` is not null;

-- --------------------------------------------------------

--
-- ビュー用の構造 `ForNode2`
--
DROP TABLE IF EXISTS `ForNode2`;

CREATE ALGORITHM=UNDEFINED DEFINER=`xs386482_u10bei`@`localhost` SQL SECURITY DEFINER VIEW `ForNode2` AS with recursive ancestor(`Depth`,`Id`,`FatherId`,`GroupName`,`Power`) as (select 0 AS `Depth`,`ForNode`.`Id` AS `Id`,`ForNode`.`FatherId` AS `FatherId`,`ForNode`.`GroupName` AS `GroupName`,`ForNode`.`Power` AS `Power` from `ForNode` where `ForNode`.`Id` = 18 or `ForNode`.`Id` = 133 or `ForNode`.`Id` = 157 union all select `ancestor`.`Depth` + 1 AS `ancestor.Depth + 1`,`ForNode`.`Id` AS `Id`,`ForNode`.`FatherId` AS `FatherId`,case when `ForNode`.`Power` = 1 then `ancestor`.`GroupName` when `ancestor`.`Power` - 1 > `ForNode`.`Power` then `ancestor`.`GroupName` else `ForNode`.`GroupName` end,case when `ancestor`.`Power` - 1 > `ForNode`.`Power` then `ancestor`.`Power` - 1 else `ForNode`.`Power` end from (`ancestor` join `ForNode`) where `ancestor`.`Id` = `ForNode`.`FatherId`)select `ancestor`.`Id` AS `Id`,`ancestor`.`GroupName` AS `GroupName` from `ancestor` order by `ancestor`.`Id`;

-- --------------------------------------------------------

--
-- ビュー用の構造 `ForPower`
--
DROP TABLE IF EXISTS `ForPower`;

CREATE ALGORITHM=UNDEFINED DEFINER=`xs386482_u10bei`@`localhost` SQL SECURITY DEFINER VIEW `ForPower` AS select `Race_Winner`.`WinnerId` AS `WinnerId`,count(`Race_Winner`.`Rtitle`) AS `Win` from `Race_Winner` group by `Race_Winner`.`WinnerId`;

-- --------------------------------------------------------

--
-- ビュー用の構造 `ForStratify`
--
DROP TABLE IF EXISTS `ForStratify`;

CREATE ALGORITHM=UNDEFINED DEFINER=`xs386482_u10bei`@`localhost` SQL SECURITY DEFINER VIEW `ForStratify` AS select `Pedigree`.`Horse` AS `From`,case when `Pedigree`.`Id` = 0 then '' else `Pedigree_1`.`Horse` end AS `To`,ifnull(`ForPower`.`Win`,0) + 1 AS `Value` from ((`Pedigree` join `Pedigree` `Pedigree_1` on(`Pedigree`.`FatherId` = `Pedigree_1`.`Id`)) left join `ForPower` on(`Pedigree`.`Id` = `ForPower`.`WinnerId`));

-- --------------------------------------------------------

--
-- ビュー用の構造 `Link`
--
DROP TABLE IF EXISTS `Link`;

CREATE ALGORITHM=UNDEFINED DEFINER=`xs386482_u10bei`@`localhost` SQL SECURITY DEFINER VIEW `Link` AS select `Pedigree`.`Horse` AS `From`,`Pedigree_1`.`Horse` AS `To`,ifnull(`ForPower`.`Win`,0) + 1 AS `Value` from ((`Pedigree` join `Pedigree` `Pedigree_1` on(`Pedigree`.`FatherId` = `Pedigree_1`.`Id`)) left join `ForPower` on(`Pedigree`.`Id` = `ForPower`.`WinnerId`)) where `Pedigree`.`Id` > 0 and `Pedigree`.`FatherId` > 0;

-- --------------------------------------------------------

--
-- ビュー用の構造 `Node`
--
DROP TABLE IF EXISTS `Node`;

CREATE ALGORITHM=UNDEFINED DEFINER=`xs386482_u10bei`@`localhost` SQL SECURITY DEFINER VIEW `Node` AS select `ForNode`.`Horse` AS `Id`,`ForNode`.`Horse` AS `Label`,`ForNode2`.`GroupName` AS `Group`,ifnull(`ForNode`.`Power`,0) + ifnull(`ForPower`.`Win`,0) AS `Value` from ((`ForNode2` left join `ForNode` on(`ForNode2`.`Id` = `ForNode`.`Id`)) left join `ForPower` on(`ForNode2`.`Id` = `ForPower`.`WinnerId`));

-- --------------------------------------------------------

--
-- ビュー用の構造 `StratifyLink`
--
DROP TABLE IF EXISTS `StratifyLink`;

CREATE ALGORITHM=UNDEFINED DEFINER=`xs386482_u10bei`@`localhost` SQL SECURITY DEFINER VIEW `StratifyLink` AS select `ForStratify`.`From` AS `From`,`ForStratify`.`To` AS `To`,`ForStratify`.`Value` AS `Value`,`ForNode`.`Power` AS `Power` from (`ForStratify` join `ForNode` on(`ForStratify`.`From` = `ForNode`.`Horse`));

--
-- Indexes for dumped tables
--

--
-- Indexes for table `Pedigree`
--
ALTER TABLE `Pedigree`
  ADD PRIMARY KEY (`Id`),
  ADD KEY `FatherId` (`FatherId`);

--
-- Indexes for table `Race_Winner`
--
ALTER TABLE `Race_Winner`
  ADD PRIMARY KEY (`Ryear`,`Rtitle`);

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
