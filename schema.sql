-- phpMyAdmin SQL Dump
-- version 5.2.3
-- https://www.phpmyadmin.net/
--
-- Host: 127.0.0.1:3306
-- Generation Time: Feb 19, 2026 at 09:07 AM
-- Server version: 8.4.7
-- PHP Version: 8.3.28

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `teacher_part`
--

-- --------------------------------------------------------

--
-- Table structure for table `admins`
--

DROP TABLE IF EXISTS `admins`;
CREATE TABLE IF NOT EXISTS `admins` (
  `admin_id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`admin_id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=MyISAM AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `admins`
--

INSERT INTO `admins` (`admin_id`, `username`, `password`) VALUES
(1, 'admin', 'admin123');

-- --------------------------------------------------------

--
-- Table structure for table `expectedanswers`
--

DROP TABLE IF EXISTS `expectedanswers`;
CREATE TABLE IF NOT EXISTS `expectedanswers` (
  `answer_id` int NOT NULL AUTO_INCREMENT,
  `answer_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `question_id` int DEFAULT NULL,
  PRIMARY KEY (`answer_id`),
  KEY `fk_question_cascade` (`question_id`)
) ENGINE=MyISAM AUTO_INCREMENT=17 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `expectedanswers`
--

INSERT INTO `expectedanswers` (`answer_id`, `answer_text`, `question_id`) VALUES
(7, 'Function calling itself...', 8),
(6, 'Random Access Memory', 7),
(5, 'A programming language...', 6),
(8, 'A programming language...', 9),
(9, 'Random Access Memory', 10),
(10, 'Function calling itself...', 11),
(11, 'A programming language...', 12),
(12, 'Random Access Memory', 13),
(13, 'Function calling itself...', 14),
(14, 'A programming language...', 15),
(15, 'Random Access Memory', 16),
(16, 'Function calling itself...', 17);

-- --------------------------------------------------------

--
-- Table structure for table `questions`
--

DROP TABLE IF EXISTS `questions`;
CREATE TABLE IF NOT EXISTS `questions` (
  `question_id` int NOT NULL AUTO_INCREMENT,
  `question_number` int DEFAULT NULL,
  `question_text` text COLLATE utf8mb4_unicode_ci NOT NULL,
  `test_id` int DEFAULT NULL,
  `max_marks` int DEFAULT '10',
  PRIMARY KEY (`question_id`),
  KEY `test_id` (`test_id`)
) ENGINE=MyISAM AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `questions`
--

INSERT INTO `questions` (`question_id`, `question_number`, `question_text`, `test_id`, `max_marks`) VALUES
(7, 2, 'Define RAM.', 8, 2),
(6, 1, 'What is Python?', 8, 5),
(8, 3, 'Explain Recursion.', 8, 10),
(9, 1, 'What is Python?', 10, 5),
(10, 2, 'Define RAM.', 10, 2),
(11, 3, 'Explain Recursion.', 10, 10),
(17, 3, 'Explain Recursion.', 11, 10),
(16, 2, 'Define RAM.', 11, 2),
(15, 1, 'What is Python?', 11, 5);

-- --------------------------------------------------------

--
-- Table structure for table `studentanswers`
--

DROP TABLE IF EXISTS `studentanswers`;
CREATE TABLE IF NOT EXISTS `studentanswers` (
  `answer_id` int NOT NULL AUTO_INCREMENT,
  `student_id` int DEFAULT NULL,
  `test_id` int DEFAULT NULL,
  `question_id` int DEFAULT NULL,
  `answer_text` text COLLATE utf8mb4_unicode_ci,
  `score` float DEFAULT NULL,
  PRIMARY KEY (`answer_id`),
  KEY `student_id` (`student_id`),
  KEY `test_id` (`test_id`),
  KEY `question_id` (`question_id`)
) ENGINE=MyISAM AUTO_INCREMENT=42 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `studentanswers`
--

INSERT INTO `studentanswers` (`answer_id`, `student_id`, `test_id`, `question_id`, `answer_text`, `score`) VALUES
(33, 3, 8, 7, 'RAN Randem Accuss 3,', 0.4),
(35, 3, 11, 15, 'Python is a programming language', 2.5),
(36, 3, 11, 16, 'Random access memory', 2),
(37, 3, 11, 17, 'Function', 3.6),
(40, 2, 8, 7, 'Random access memory', 2),
(39, 2, 8, 6, 'Python is a programming language', 2.5),
(41, 2, 8, 8, 'Function', 3.6);

-- --------------------------------------------------------

--
-- Table structure for table `students`
--

DROP TABLE IF EXISTS `students`;
CREATE TABLE IF NOT EXISTS `students` (
  `student_id` int NOT NULL AUTO_INCREMENT,
  `registration_no` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `rollno` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `email` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `age` int DEFAULT NULL,
  `gender` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `student_class` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `address` text COLLATE utf8mb4_unicode_ci,
  `status` enum('pending','approved','rejected') COLLATE utf8mb4_unicode_ci DEFAULT 'pending',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`student_id`),
  UNIQUE KEY `registration_no` (`registration_no`),
  UNIQUE KEY `rollno` (`rollno`),
  UNIQUE KEY `email` (`email`)
) ENGINE=MyISAM AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `students`
--

INSERT INTO `students` (`student_id`, `registration_no`, `rollno`, `email`, `password`, `name`, `age`, `gender`, `student_class`, `address`, `status`, `created_at`) VALUES
(1, '2002044655', '32', 'shalwin@gmail.com', 'shalwin123', 'shalwin ps', 22, 'Male', 'CSE', 'kochi', 'approved', '2026-02-12 12:24:46'),
(2, '200204465545', '15', 'ashik@gmail.com', 'ashik123', 'ashik', 23, 'Male', '10', 'parvur', 'approved', '2026-02-13 07:14:29'),
(3, '20020446554556', '11', 'rahul@gmail.com', 'rahul@123', 'rahul', 11, 'Male', '10', 'parvur', 'approved', '2026-02-15 06:48:27');

-- --------------------------------------------------------

--
-- Table structure for table `teachers`
--

DROP TABLE IF EXISTS `teachers`;
CREATE TABLE IF NOT EXISTS `teachers` (
  `teacher_id` int NOT NULL AUTO_INCREMENT,
  `email` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('pending','approved','rejected') COLLATE utf8mb4_unicode_ci DEFAULT 'pending',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `gender` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `department` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `address` text COLLATE utf8mb4_unicode_ci,
  `phone` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`teacher_id`),
  UNIQUE KEY `email` (`email`)
) ENGINE=MyISAM AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `teachers`
--

INSERT INTO `teachers` (`teacher_id`, `email`, `password`, `name`, `status`, `created_at`, `gender`, `department`, `address`, `phone`) VALUES
(1, 'yadhu@gmail.com', 'yadhudev@123', 'yadhudev ps', 'approved', '2026-02-12 12:05:34', 'Male', 'CSE', 'kochi', '8590924788');

-- --------------------------------------------------------

--
-- Table structure for table `teacherstudentrelationship`
--

DROP TABLE IF EXISTS `teacherstudentrelationship`;
CREATE TABLE IF NOT EXISTS `teacherstudentrelationship` (
  `id` int NOT NULL AUTO_INCREMENT,
  `teacher_id` int DEFAULT NULL,
  `student_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `teacher_id` (`teacher_id`),
  KEY `student_id` (`student_id`)
) ENGINE=MyISAM DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Table structure for table `tests`
--

DROP TABLE IF EXISTS `tests`;
CREATE TABLE IF NOT EXISTS `tests` (
  `test_id` int NOT NULL AUTO_INCREMENT,
  `test_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `teacher_id` int DEFAULT NULL,
  `test_class` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (`test_id`),
  KEY `teacher_id` (`teacher_id`)
) ENGINE=MyISAM AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Dumping data for table `tests`
--

INSERT INTO `tests` (`test_id`, `test_name`, `teacher_id`, `test_class`) VALUES
(10, 'sample', 1, '+2'),
(8, '1st internal computer', 1, '10'),
(11, 'test 2', 1, '10');
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
