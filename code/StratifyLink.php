<?php
    //接続情報は、自分のサーバの情報に置き換えてください。
    $conn = mysqli_connect("hostname", "username", "password", "database");

    if($conn){
    }else{
      echo "データベースに接続できません";
    }
    
    $result = mysqli_query($conn, "SELECT * FROM StratifyLink");
 
    if(mysqli_num_rows($result) == 0){
      echo "レコードが有りません";
    }
 
    while($row = mysqli_fetch_assoc($result)){
         $data[] = $row;
    } 
 
    //値をjson形式で出力（ちょっとインチキ）
    header("Access-Control-Allow-Origin: *");
    echo json_encode($data);
?>