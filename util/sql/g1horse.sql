-- --------------------------------------------------------
-- ホスト:                          127.0.0.1
-- サーバーのバージョン:                   10.9.2-MariaDB - mariadb.org binary distribution
-- サーバー OS:                      Win64
-- HeidiSQL バージョン:               11.3.0.6295
-- --------------------------------------------------------

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET NAMES utf8 */;
/*!50503 SET NAMES utf8mb4 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--  ビュー xs386482_g1horse.forgroup の構造をダンプしています
-- VIEW 依存エラーを克服するために、一時テーブルを作成
CREATE TABLE `forgroup` (
	`FatherId` SMALLINT(6) NULL,
	`Horse` VARCHAR(20) NOT NULL COLLATE 'utf8mb4_general_ci',
	`Child` BIGINT(21) NOT NULL
) ENGINE=MyISAM;

--  ビュー xs386482_g1horse.forlink の構造をダンプしています
-- VIEW 依存エラーを克服するために、一時テーブルを作成
CREATE TABLE `forlink` (
	`FatherId` SMALLINT(6) NULL,
	`Child` BIGINT(21) NOT NULL
) ENGINE=MyISAM;

--  ビュー xs386482_g1horse.fornode の構造をダンプしています
-- VIEW 依存エラーを克服するために、一時テーブルを作成
CREATE TABLE `fornode` (
	`Id` SMALLINT(6) NOT NULL,
	`Horse` VARCHAR(20) NOT NULL COLLATE 'utf8mb4_general_ci',
	`FatherId` SMALLINT(6) NULL,
	`GroupId` SMALLINT(6) NULL,
	`GroupName` VARCHAR(20) NULL COLLATE 'utf8mb4_general_ci',
	`Power` BIGINT(22) NOT NULL
) ENGINE=MyISAM;

--  ビュー xs386482_g1horse.fornode2 の構造をダンプしています
-- VIEW 依存エラーを克服するために、一時テーブルを作成
CREATE TABLE `fornode2` (
	`Id` SMALLINT(6) NULL,
	`GroupName` VARCHAR(20) NULL COLLATE 'utf8mb4_general_ci'
) ENGINE=MyISAM;

--  ビュー xs386482_g1horse.forpower の構造をダンプしています
-- VIEW 依存エラーを克服するために、一時テーブルを作成
CREATE TABLE `forpower` (
	`WinnerId` SMALLINT(6) NOT NULL,
	`Win` BIGINT(21) NOT NULL
) ENGINE=MyISAM;

--  ビュー xs386482_g1horse.forstratify の構造をダンプしています
-- VIEW 依存エラーを克服するために、一時テーブルを作成
CREATE TABLE `forstratify` (
	`from` VARCHAR(20) NOT NULL COLLATE 'utf8mb4_general_ci',
	`to` VARCHAR(20) NOT NULL COLLATE 'utf8mb4_general_ci',
	`value` BIGINT(22) NOT NULL
) ENGINE=MyISAM;

--  ビュー xs386482_g1horse.link の構造をダンプしています
-- VIEW 依存エラーを克服するために、一時テーブルを作成
CREATE TABLE `link` (
	`from` VARCHAR(20) NOT NULL COLLATE 'utf8mb4_general_ci',
	`to` VARCHAR(20) NOT NULL COLLATE 'utf8mb4_general_ci',
	`value` BIGINT(22) NOT NULL
) ENGINE=MyISAM;

--  ビュー xs386482_g1horse.node の構造をダンプしています
-- VIEW 依存エラーを克服するために、一時テーブルを作成
CREATE TABLE `node` (
	`id` VARCHAR(20) NULL COLLATE 'utf8mb4_general_ci',
	`label` VARCHAR(20) NULL COLLATE 'utf8mb4_general_ci',
	`group` VARCHAR(20) NULL COLLATE 'utf8mb4_general_ci',
	`value` BIGINT(23) NOT NULL
) ENGINE=MyISAM;

--  テーブル xs386482_g1horse.pedigree の構造をダンプしています
CREATE TABLE IF NOT EXISTS `pedigree` (
  `Id` smallint(6) NOT NULL,
  `Horse` varchar(20) NOT NULL,
  `FatherId` smallint(6) DEFAULT NULL,
  PRIMARY KEY (`Id`),
  KEY `FatherId` (`FatherId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- エクスポートするデータが選択されていません

--  テーブル xs386482_g1horse.race_winner の構造をダンプしています
CREATE TABLE IF NOT EXISTS `race_winner` (
  `Ryear` smallint(6) NOT NULL,
  `Rtitle` varchar(50) NOT NULL,
  `WinnerId` smallint(6) NOT NULL,
  PRIMARY KEY (`Ryear`,`Rtitle`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- エクスポートするデータが選択されていません

--  ビュー xs386482_g1horse.stratifylink の構造をダンプしています
-- VIEW 依存エラーを克服するために、一時テーブルを作成
CREATE TABLE `stratifylink` (
	`from` VARCHAR(20) NOT NULL COLLATE 'utf8mb4_general_ci',
	`to` VARCHAR(20) NOT NULL COLLATE 'utf8mb4_general_ci',
	`value` BIGINT(22) NOT NULL,
	`Power` BIGINT(22) NOT NULL
) ENGINE=MyISAM;

--  ビュー xs386482_g1horse.forgroup の構造をダンプしています
-- 一時テーブルを削除して、最終的な VIEW 構造を作成
DROP TABLE IF EXISTS `forgroup`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `forgroup` AS SELECT ForLink.FatherId, Pedigree.Horse, ForLink.Child
FROM ForLink INNER JOIN Pedigree ON ForLink.FatherId = Pedigree.Id
WHERE ((ForLink.Child)>1) 
ORDER BY ForLink.Child DESC, ForLink.FatherId ASC ;

--  ビュー xs386482_g1horse.forlink の構造をダンプしています
-- 一時テーブルを削除して、最終的な VIEW 構造を作成
DROP TABLE IF EXISTS `forlink`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `forlink` AS SELECT Pedigree.FatherId, Count(Pedigree.FatherId) AS Child
FROM Pedigree
GROUP BY Pedigree.FatherId
HAVING (((Pedigree.FatherId)>0)) ;

--  ビュー xs386482_g1horse.fornode の構造をダンプしています
-- 一時テーブルを削除して、最終的な VIEW 構造を作成
DROP TABLE IF EXISTS `fornode`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `fornode` AS SELECT
	Pedigree.Id,
	Pedigree.Horse,
	Pedigree.FatherId,
	ForGroup.FatherId AS GroupId,
	ForGroup.Horse AS GroupName,
	ifnull(ForGroup.Child, 0) + 1 AS Power
FROM Pedigree LEFT JOIN ForGroup ON Pedigree.Id = ForGroup.FatherId
WHERE Pedigree.FatherId IS NOT NULL ;

--  ビュー xs386482_g1horse.fornode2 の構造をダンプしています
-- 一時テーブルを削除して、最終的な VIEW 構造を作成
DROP TABLE IF EXISTS `fornode2`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `fornode2` AS WITH RECURSIVE ancestor (Depth, Id, FatherId, GroupName, Power) AS (
      SELECT 0, ForNode.Id, ForNode.FatherId, ForNode.GroupName, ForNode.Power FROM ForNode 
			WHERE (ForNode.Id = 18 OR ForNode.Id = 133 OR ForNode.Id = 157)
		UNION ALL
        SELECT 
            ancestor.Depth + 1,
            ForNode.Id,
            ForNode.FatherId,
            CASE
            	WHEN ForNode.Power = 1 THEN  ancestor.GroupName
            	WHEN ancestor.Power - 1 > ForNode.Power THEN ancestor.GroupName
            	ELSE ForNode.GroupName
				END,
            CASE
					WHEN ancestor.Power - 1 > ForNode.Power THEN ancestor.Power - 1
            	ELSE ForNode.Power
				END			
        FROM ancestor, ForNode
        WHERE ancestor.Id = ForNode.FatherId)
SELECT Id, GroupName FROM ancestor ORDER BY Id ;

--  ビュー xs386482_g1horse.forpower の構造をダンプしています
-- 一時テーブルを削除して、最終的な VIEW 構造を作成
DROP TABLE IF EXISTS `forpower`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `forpower` AS SELECT Race_Winner.WinnerId, Count(Race_Winner.Rtitle) AS Win
FROM Race_Winner
GROUP BY Race_Winner.WinnerId ;

--  ビュー xs386482_g1horse.forstratify の構造をダンプしています
-- 一時テーブルを削除して、最終的な VIEW 構造を作成
DROP TABLE IF EXISTS `forstratify`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `forstratify` AS SELECT Pedigree.Horse AS `from`,
	case
	 when Pedigree.Id = 0 then ''
	 else Pedigree_1.Horse
	end AS `to`,
	IFNULL( ForPower.Win,0 ) + 1 AS `value`
from ((Pedigree join Pedigree AS Pedigree_1 on(Pedigree.FatherId = Pedigree_1.Id))
 left join ForPower on(Pedigree.Id = ForPower.WinnerId)) ;

--  ビュー xs386482_g1horse.link の構造をダンプしています
-- 一時テーブルを削除して、最終的な VIEW 構造を作成
DROP TABLE IF EXISTS `link`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `link` AS SELECT Pedigree.Horse AS 'from', Pedigree_1.Horse AS 'to', ifnull(ForPower.Win,0)+1 AS 'value'
FROM (Pedigree INNER JOIN Pedigree AS Pedigree_1 ON Pedigree.FatherId = Pedigree_1.Id) LEFT OUTER JOIN ForPower ON Pedigree.Id = ForPower.WinnerId
WHERE (Pedigree.Id >0 AND Pedigree.FatherId >0) ;

--  ビュー xs386482_g1horse.node の構造をダンプしています
-- 一時テーブルを削除して、最終的な VIEW 構造を作成
DROP TABLE IF EXISTS `node`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `node` AS SELECT ForNode.Horse AS id, ForNode.Horse AS label, ForNode2.GroupName AS 'group', ifnull(ForNode.Power,0)+ifnull(ForPower.Win,0) AS 'value'
FROM (ForNode2 LEFT OUTER JOIN ForNode ON ForNode2.Id = ForNode.Id) LEFT OUTER JOIN ForPower ON ForNode2.Id = ForPower.WinnerId ;

--  ビュー xs386482_g1horse.stratifylink の構造をダンプしています
-- 一時テーブルを削除して、最終的な VIEW 構造を作成
DROP TABLE IF EXISTS `stratifylink`;
CREATE ALGORITHM=UNDEFINED SQL SECURITY DEFINER VIEW `stratifylink` AS SELECT ForStratify.`from`,
	ForStratify.`to`,
	ForStratify.value,
	fornode.Power
from (ForStratify join ForNode on(ForStratify.`from` = fornode.Horse)) ;

/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
