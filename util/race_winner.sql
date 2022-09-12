CREATE TABLE `race_winner` (
	`Ryear` SMALLINT(6) NOT NULL,
	`Rtitle` VARCHAR(50) NOT NULL COLLATE 'utf8mb4_general_ci',
	`WinnerId` SMALLINT(6) NOT NULL,
	PRIMARY KEY (`Ryear`, `Rtitle`) USING BTREE
)
COLLATE='utf8mb4_general_ci'
ENGINE=InnoDB
;